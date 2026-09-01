#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#
## RandomWoods Forecast
##
## Refactored from RF-v3.2.2---ForecastMode_WY2026_Mod.Rmd for
## non-interactive execution (Rscript / subprocess from a future
## Python Prefect flow). Behavior matches the original notebook;
## changes are limited to:
##   - removing RMarkdown chunk fences
##   - parameterizing endYear, input filenames, and I/O directories
##     via environment variables (with the original hardcoded values
##     kept as fallbacks)
##   - resolving the library `source()` path relative to this script,
##     not the caller's working directory
##   - failing loudly (non-zero exit code) on error, so a Prefect task
##     wrapping this script can detect failures
##   - all plot/PNG/PDF generation (ggplot2/gghalves/patchwork,
##     diagnostic PDF) removed -- operational runs only need
##     WY{year}.Forecast.csv, and this keeps the Docker image and its
##     R dependencies minimal
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#

#### CLEAR MEMORY
rm(list = ls())
options(warnings = -1)

# ---- Fail loudly: non-zero exit code on any uncaught error ----
# This lets a Python subprocess wrapper (Prefect task) detect failures
# via the process return code instead of having to parse stdout.
options(error = function() {
  cat("RandomWoods forecast FAILED:\n")
  traceback(2)
  quit(status = 1, save = "no")
})

# ---- Packages ----
library(zoo)
library(dplyr)
library(stringr)
library(readxl)
library(randomForest)
library(tidyr)

# ---- Resolve this script's own directory (works under Rscript, RStudio, or source()) ----
get_script_dir <- function() {
  cmd_args <- commandArgs(trailingOnly = FALSE)
  file_arg <- sub("^--file=", "", cmd_args[grepl("^--file=", cmd_args)])
  if (length(file_arg) > 0) {
    return(dirname(normalizePath(file_arg)))
  }
  # Fallback for interactive/RStudio sessions
  if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
    return(dirname(rstudioapi::getSourceEditorContext()$path))
  }
  getwd()
}
script_dir <- get_script_dir()

source(file.path(script_dir, "year2_randomForest_library_v1.2.1.R"))

# ---- Environment-variable-driven configuration ----
# WORK_DIR: directory containing the *annually updated* naturalized-flow
# workbook, and where outputs are written. Defaults to the script's own
# directory so it still runs standalone.
work_dir <- Sys.getenv("WORK_DIR", unset = script_dir)
setwd(work_dir)

# STATIC_DATA_DIR: directory containing the CESM-LE quantile files. These
# never change until after WY2080, so
# they're kept separate from WORK_DIR and baked into the Docker image
# rather than needing to be supplied per run. Defaults to
# .../randomwoods/static_data, resolved relative to this script (this whole
# randomwoods/ folder is self-contained and gets copied into the image).
static_data_dir <- Sys.getenv("STATIC_DATA_DIR", unset = normalizePath(
  file.path(script_dir, "..", "static_data"), mustWork = FALSE
))

# FORECAST_YEAR: water year to forecast. Water year starts Oct 1, so if the
# system month is >= October, the forecast targets the *next* calendar year.
end_year_env <- Sys.getenv("FORECAST_YEAR", unset = "")
endYear <- if (nchar(end_year_env) > 0) {
  as.integer(end_year_env)
} else {
  current_month <- as.integer(format(Sys.Date(), "%m"))
  current_year  <- as.integer(format(Sys.Date(), "%Y"))
  if (current_month >= 10) current_year + 1L else current_year
}

# Input filenames (overridable; defaults preserve original repo filenames
# where a standardized name isn't yet in use).
# - lf_natflow_file, amo_file, pdo_file are resolved against WORK_DIR
#   (annual data, refreshed once a year -- see workflows/ingests/).
# - the three CESM-LE files are resolved against STATIC_DATA_DIR (static data).
lf_natflow_file <- Sys.getenv("LF_NATFLOW_FILE", unset = "LFnatFlow1906-2024.2024.9.12.xlsx")
amo_file        <- Sys.getenv("AMO_FILE", unset = "AMO_latest.dat")
pdo_file        <- Sys.getenv("PDO_FILE", unset = "PDO_latest.dat")
tmax_le_file    <- file.path(static_data_dir, Sys.getenv("TMAX_LE_FILE", unset = "TREFHTMX_quantile_UCO_1920-2080.txt"))
tmin_le_file    <- file.path(static_data_dir, Sys.getenv("TMIN_LE_FILE", unset = "TREFHTMN_quantile_UCO_1920-2080.txt"))
pcp_le_file     <- file.path(static_data_dir, Sys.getenv("PCP_LE_FILE",  unset = "PRECT_quantile_UCO_1920-2080.txt"))

# Output directory (created if missing). Defaults to WORK_DIR (original behavior).
output_dir <- Sys.getenv("OUTPUT_DIR", unset = work_dir)
dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

# RANDOM_SEED: the original notebook did not seed the RNG, so randomForest's
# bootstrap sampling made ensemble mean/median/IQR vary slightly on every
# run. Fixing a seed makes a given (data, endYear) combination reproducible
# run-to-run -- important for an automated/scheduled job. Override via env
# var if a different seed is ever needed (e.g. for sensitivity testing).
random_seed <- as.integer(Sys.getenv("RANDOM_SEED", unset = "42"))
set.seed(random_seed)
cat("Random seed:", random_seed, "\n")

cat("RandomWoods starting. Forecast year:", endYear, "\n")
cat("Working directory:", getwd(), "\n")
cat("Static data directory:", static_data_dir, "\n")
cat("Output directory:", output_dir, "\n")

### Read data and pre-process
#
# AMO/PDO are read from local files in WORK_DIR, same as the naturalized
# flow workbook -- downloaded once a year alongside it (see
# workflows/ingests/ocean_indices/) rather than fetched live from NOAA on
# every forecast run. This model only runs annually right before Oct 1, by
# which point the JAS (Jul-Aug-Sep) mean these indices feed into is already
# final, so there's no benefit to a live fetch -- only an extra network
# dependency and a loss of run-to-run reproducibility (NOAA does
# occasionally revise historical months in place).
amo0 = read.csv(amo_file, sep = "", header = T, skip = 1)
pdo0 = read.csv(pdo_file, sep = "", header = T, skip = 1, na.strings = "99.99")

### Read annual WY flows
# Dynamic read: no hardcoded row range, so this keeps working as new rows
# (water years) are appended to the workbook in future years. USBR appends
# trailing "1906-2020 average" / "1991-2020 average" summary rows below the
# data, whose year column is text rather than blank -- so we must coerce to
# integer *first* and drop rows that fail to parse as a water year, rather
# than filtering on raw NA-ness beforehand.
annFlows = read_excel(lf_natflow_file, sheet = 1, col_names = F, skip = 3)
annFlows$wyears = suppressWarnings(as.integer(annFlows[[1]]))
annFlows$q_maf  = suppressWarnings(as.numeric(annFlows[[2]])) / 10^6
annFlows = annFlows[!is.na(annFlows$wyears) & !is.na(annFlows$q_maf), c("wyears", "q_maf")]

# ---- Optional manual prior-year flow override ----
# Only needed if LF_NATFLOW_FILE has not yet been updated with the latest
# completed water year (e.g. a preliminary USBR estimate). Set the
# MANUAL_PRIOR_WY / MANUAL_PRIOR_QMAF env vars to enable; otherwise this is
# a no-op and the workbook's own latest row is used, matching how the
# original notebook's hardcoded `add_row(annFlows, wyears = 2025, q_maf = 8.502)`
# was intended to be applied.
manual_prior_wy    <- Sys.getenv("MANUAL_PRIOR_WY", unset = "")
manual_prior_q_maf <- Sys.getenv("MANUAL_PRIOR_QMAF", unset = "")
if (nchar(manual_prior_wy) > 0 && nchar(manual_prior_q_maf) > 0) {
  manual_wy <- as.integer(manual_prior_wy)
  if (!manual_wy %in% annFlows$wyears) {
    cat("Adding manual prior-year flow override: WY", manual_wy, "=", manual_prior_q_maf, "MAF\n")
    annFlows <- tibble::add_row(annFlows, wyears = manual_wy, q_maf = as.numeric(manual_prior_q_maf))
  }
}
annFlows <- dplyr::arrange(annFlows, wyears)

library(dplyr)
library(zoo)

k = 20

q20 = annFlows %>%
  mutate(
    q_maf = zoo::rollmean(q_maf, k, align = "right", fill = NA)
  ) %>%
  mutate(
    end_year   = wyears,
    start_year = wyears - (k - 1)
  ) %>%
  filter(!is.na(q_maf))

###----------------------------------------------------------------------------------------------------------------
### Read in and process CESM LE or LME MONTHLY data
#Tmax
Tmax.le = read.csv(file = tmax_le_file, sep = "")
yearmo = Tmax.le$yearmoth

#Tmin
Tmin.le = read.csv(file = tmin_le_file, sep = "")

#precip
pcp.le = read.csv(file = pcp_le_file, sep = "")

# calc ensemble mean
ensMean.Tmax.C = apply(Tmax.le[,2:6], 1, mean) - 273.15
ensMean.Tmin.C = apply(Tmin.le[,2:6], 1, mean) - 273.15
ensMean.pcp.mm = apply(pcp.le[,2:6], 1, mean)

#all quantiles
le.monthly = cbind(yearmo, ensMean.Tmax.C, ensMean.Tmin.C, ensMean.pcp.mm)

### calc annual (water year) covariates from CESM-LE
#remove first 8 rows of le.seas to prepare for water year format and remove all rows after 082017 to match end of record for obs flows
le.monthly.sub = subset(le.monthly, yearmo >= 192010 & yearmo <= endYear*100+09)
le.wyears = 1921:endYear

###------------------------------------------------------------------------------------------------------------------------
#LE UCRB simulated data
le.pcp.wy.mon = longToWide(le.monthly.sub[,c(1,4)], le.wyears, "pcp", endYear) #inches
le.tmin.wy.mon = longToWide(le.monthly.sub[,c(1,3)], le.wyears, "tmin", endYear) #deg C
le.tmax.wy.mon = longToWide(le.monthly.sub[,c(1,2)], le.wyears, "tmax", endYear) #deg C

#remove a few rows of meta data at the end of data frame
startYear = 1921

stats = annFlows
stats = subset(stats, wyears >= startYear)

amo = pivot_wider(amo0, names_from = month, values_from = SSTA)
colnames(amo) = colnames(pdo0)
amo.wy = waterYearFormatting(amo, stats)

pdo = pdo0
pdo.wy = waterYearFormatting(pdo, stats)

#oct 1 forecast of wy flow
#0 month lead time
df.y1.oct = data.frame(stats[-1,],
                       pdo = rowMeans(head(pdo.wy[,11:13], -1)),
                       amo = rowMeans(head(amo.wy[,11:13], -1)),
                       LE.Tmin = rowMeans(head(le.tmin.wy.mon[-1,-1], -1)),
                       LE.Pcp = rowSums(head(le.pcp.wy.mon[-1,-1], -1))
                      )

forecast.covariates = data.frame(
                       pdo = rowMeans(tail(pdo.wy[,11:13], 1)),
                       amo = rowMeans(tail(amo.wy[,11:13], 1)),
                       LE.Tmin = rowMeans(tail(le.tmin.wy.mon[,-1], 1)),
                       LE.Pcp = rowSums(tail(le.pcp.wy.mon[,-1], 1))
                      )

# ---- Core: train RF, predict, and compute ensemble stats ----
rf.train = randomForest(q_maf ~ ., data = df.y1.oct[,-1], ntree = 600, importance = T)

fcst.rf = predict(rf.train, newdata = forecast.covariates, predict.all = TRUE)

ensMean = mean(as.numeric(fcst.rf$individual))
ensMedian = median(as.numeric(fcst.rf$individual))
ensQuants = quantile(as.numeric(fcst.rf$individual))
ens25 = ensQuants[2]
ens75 = ensQuants[4]

cat("Ensemble mean = ", ensMean, "\n")
cat("Ensemble median = ", ensMedian, "\n")

stats.mod = rbind(stats, c(endYear, fcst.rf$aggregate))

df = data.frame(wyears = rep(endYear, 600), q_maf = as.numeric(as.character(fcst.rf$individual)))

stats.mod2 = rbind(stats, df)

# ---- Primary output: forecast ensemble CSV ----
fout = file.path(output_dir, paste0("WY", endYear, ".Forecast.csv"))
write.csv(stats.mod2[stats.mod2$wyears == endYear,], fout, row.names = F)

cat("RandomWoods WY", endYear, "forecast complete.\n")
cat("Ensemble mean =", ensMean, " median =", ensMedian, " IQR =", ens25, "-", ens75, "MAF\n")
