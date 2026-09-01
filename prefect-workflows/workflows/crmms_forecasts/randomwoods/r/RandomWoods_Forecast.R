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
##   - writing key diagnostic base-R plots (variable importance,
##     ensemble boxplot, updated flow series) to a PDF for logging,
##     since base graphics are otherwise silently dropped under Rscript
##   - making all plot/PNG/PDF generation optional via GENERATE_PLOTS,
##     since an operational run only needs WY{year}.Forecast.csv. This
##     also means ggplot2/gghalves/patchwork are only loaded (and only
##     need to be installed in the Docker image) when plots are enabled.
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
# ggplot2 / gghalves / patchwork are plotting-only and loaded further below,
# conditional on GENERATE_PLOTS, so a "no plots" operational run doesn't
# require them to be installed at all.
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

# GENERATE_PLOTS: an operational/scheduled run only needs the forecast CSV.
# Set to "false"/"0" to skip all PNG/PDF generation (and avoid needing
# ggplot2/gghalves/patchwork installed at all -- see Dockerfile).
generate_plots <- tolower(Sys.getenv("GENERATE_PLOTS", unset = "true")) %in% c("true", "1", "yes")
if (generate_plots) {
  library(ggplot2)
  library(gghalves) # archived from CRAN; install via remotes::install_github("erocoar/gghalves")
  library(patchwork)
}
cat("Generate plots:", generate_plots, "\n")

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

# ---- Core: train RF, predict, and compute ensemble stats (always needed
# for the CSV output, regardless of GENERATE_PLOTS) ----
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

# ---- Primary output: forecast ensemble CSV (always written) ----
fout = file.path(output_dir, paste0("WY", endYear, ".Forecast.csv"))
write.csv(stats.mod2[stats.mod2$wyears == endYear,], fout, row.names = F)

if (!generate_plots) {
  cat("GENERATE_PLOTS=false -- skipping plot/PNG/PDF generation (CSV-only run)\n")
} else {

# ---- Diagnostic PDF: captures base-R plots that would otherwise be
# silently dropped when this script runs headless under Rscript ----
diag_pdf <- file.path(output_dir, paste0("WY", endYear, ".Diagnostics.pdf"))
pdf(diag_pdf)

#create variable importance for RF
vip.j = varImpPlot(rf.train, cex.main = 0.8)

boxplot(as.numeric(fcst.rf$individual))
points(fcst.rf$aggregate, col = "red")

plot(stats.mod, type = "l")
points(stats.mod, pch = 16, cex = 0.5)

boxplot(q_maf ~ wyears, data = stats.mod2, xlab = "Water Year", ylab = "Lees Ferry Flow (MAF)")
lines(q_maf ~ wyears, data = stats.mod2)

dev.off()

# ---- Forecast distribution plot (historical series + WY forecast) ----
ggplot(data = subset(stats.mod2, wyears < endYear), aes(x = wyears, y = q_maf, group = wyears)) +
  geom_point(size = 0.6) +
  coord_cartesian(xlim = c(1925, endYear)) +
  geom_half_violin(data = stats.mod2[stats.mod2$wyears == endYear,], aes(x = wyears, y = q_maf, group = wyears), fill = "green", trim = T, alpha = 0.75, side = "r", width = 10) +
  geom_boxplot(data = stats.mod2[stats.mod2$wyears == endYear,], aes(x = wyears, y = q_maf, group = wyears), fill = "green", alpha = 0.75) +
  xlab("Water Year") + ylab("Lees Ferry Naturalized Flow (MAF)") +
  geom_line(data = subset(stats.mod2, wyears < endYear), aes(x = wyears, y = q_maf, group = 1)) +
  theme_bw() + theme(axis.title = element_text(face = "bold")) +
  ggtitle(paste0("randomWoods Forecast\nWater year ", endYear, " most probable forecast (50th percentile) = ", round(ensMedian, digits = 1), "-MAF\nInterquartile Range = ", round(ens25, digits = 1), "- to ", round(ens75, digits = 1), "-MAF"))

ggsave(file.path(output_dir, paste0("WY", endYear, ".Forecast.png")), dpi = 900)

# ---- Ocean index (PDO/AMO) + flow overlay ----
df_plot <- df.y1.oct %>%
  mutate(
    PDO_roll11 = rollapply(pdo, 11, mean, fill = NA, align = "center"),
    AMO_roll11 = rollapply(amo, 11, mean, fill = NA, align = "center"),
    Q_roll11   = rollapply(q_maf, 11, mean, fill = NA, align = "center")
  )

range_idx <- range(c(df_plot$pdo, df_plot$amo), na.rm = TRUE)
range_q   <- range(df_plot$q_maf, na.rm = TRUE)
scale_fac <- diff(range_idx) / diff(range_q)
offset    <- mean(range_idx) - scale_fac * mean(range_q)

df_plot <- df_plot %>%
  mutate(q_scaled = q_maf * scale_fac + offset,
         q_roll11_scaled = Q_roll11 * scale_fac + offset)

p_ocean = ggplot(df_plot, aes(x = wyears)) +
  geom_line(aes(y = q_scaled), color = "black", linewidth = 0.5, alpha = 0.5) +
  geom_line(aes(y = q_roll11_scaled), color = "black", linewidth = 1) +
  geom_line(aes(y = pdo, color = "PDO"), linewidth = 0.5, alpha = 0.5) +
  geom_line(aes(y = PDO_roll11, color = "PDO"), linewidth = 1) +
  geom_line(aes(y = amo, color = "AMO"), linewidth = 0.5, alpha = 0.5) +
  geom_line(aes(y = AMO_roll11, color = "AMO"), linewidth = 1) +
  geom_hline(yintercept = 0, linetype = "dashed", color = "black", linewidth = 0.3) +
  scale_color_manual(values = c(PDO = "#1f77b4", AMO = "#d62728")) +
  scale_y_continuous(
    name = "Climate Index",
    sec.axis = sec_axis(~ (. - offset) / scale_fac,
                        name = "Flow (MAF)")
  ) +
  labs(
    x = "Water year",
    title = "JAS (Jul–Aug–Sep) Mean PDO & AMO with Annual Flow",
    subtitle = "Thick lines = 11-year running means; flow shown on right axis",
    color = "Index"
  ) +
  theme_minimal(base_size = 12) +
  theme(
    legend.position = "top",
    panel.grid.minor = element_blank(),
    plot.title.position = "plot"
  )

ggsave(file.path(output_dir, "oceanIndexTimeSeries.png"), p_ocean, dpi = 900)

# ---- CESM-LE covariates + flow overlay ----
df_le = df.y1.oct %>%
  mutate(
    LE.Tmin_z = as.numeric(scale(LE.Tmin)),
    LE.Pcp_z  = as.numeric(scale(LE.Pcp)),
    Tmin_roll11 = rollapply(LE.Tmin_z, 11, mean, fill = NA, align = "center"),
    Pcp_roll11  = rollapply(LE.Pcp_z,  11, mean, fill = NA, align = "center"),
    Q_roll11    = rollapply(q_maf,     11, mean, fill = NA, align = "center")
  )

range_idx = range(c(df_le$LE.Tmin_z, df_le$LE.Pcp_z), na.rm = TRUE)
range_q   = range(df_le$q_maf, na.rm = TRUE)

scale_fac = diff(range_idx) / diff(range_q)
offset    = mean(range_idx) - scale_fac * mean(range_q)

df_le = df_le %>%
  mutate(
    q_scaled        = q_maf   * scale_fac + offset,
    q_roll11_scaled = Q_roll11 * scale_fac + offset
  )

p_le = ggplot(df_le, aes(x = wyears)) +
  geom_line(aes(y = q_scaled), color = "black", linewidth = 0.5, alpha = 0.35) +
  geom_line(aes(y = q_roll11_scaled), color = "black", linewidth = 1.1) +
  geom_line(aes(y = LE.Tmin_z, color = "LE Tmin"), linewidth = 0.5, alpha = 0.45) +
  geom_line(aes(y = Tmin_roll11, color = "LE Tmin"), linewidth = 1.1) +
  geom_line(aes(y = LE.Pcp_z,  color = "LE Pcp"),  linewidth = 0.5, alpha = 0.45) +
  geom_line(aes(y = Pcp_roll11,  color = "LE Pcp"),  linewidth = 1.1) +
  geom_hline(yintercept = 0, linetype = "dashed", color = "black", linewidth = 0.3) +
  scale_color_manual(
    values = c(
      "LE Tmin" = "#D55E00",
      "LE Pcp"  = "#0072B2"
    )
  ) +
  scale_y_continuous(
    name = "CESM-LE covariates (standardized)",
    sec.axis = sec_axis(~ (. - offset) / scale_fac, name = "Flow (MAF)")
  ) +
  labs(
    x = "Water year",
    title = "CESM-LE Covariates with Annual Flow",
    subtitle = "Thick lines = 11-year running means; flow shown on right axis",
    color = "Covariate"
  ) +
  theme_minimal(base_size = 12) +
  theme(
    legend.position = "top",
    panel.grid.minor = element_blank(),
    plot.title.position = "plot"
  )

ggsave(file.path(output_dir, "cesmLE_covariates_timeSeries.png"), p_le, dpi = 900, width = 12, height = 6)

# ---- Combined ocean + CESM-LE panel ----
# (patchwork already loaded above, conditional on generate_plots)

p_ocean2 =
  p_ocean +
  theme(
    axis.title.x = element_blank(),
    axis.text.x  = element_blank(),
    axis.ticks.x = element_blank(),
    plot.margin  = ggplot2::margin(t = 6, r = 6, b = 0, l = 6, unit = "pt")
  ) +
  labs(color = NULL)

p_le2 =
  p_le +
  theme(
    plot.margin = ggplot2::margin(t = 0, r = 6, b = 6, l = 6, unit = "pt")
  ) +
  labs(color = NULL)

p_combo =
  (p_ocean2 / p_le2) +
  plot_layout(heights = c(1, 1)) &
  theme(legend.position = "top")

ggsave(file.path(output_dir, "ocean_plus_CESMLE_timeseries.png"), p_combo, dpi = 900, width = 13, height = 10)

} # end if (generate_plots)

cat("RandomWoods WY", endYear, "forecast complete.\n")
cat("Ensemble mean =", ensMean, " median =", ensMedian, " IQR =", ens25, "-", ens75, "MAF\n")
