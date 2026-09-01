#############################################################################################################
#############################################################################################################
#############################################################################################################

#put monthly climate indicies into water year format and calc averages where applicable

#remove a few rows of meta data at the end of data frame
#amo = head(amo0, -4)
# df0 = amo

waterYearFormatting = function(df0, stats){
  
  #convert data to numeric (original data is a mix of factors and doubles which causes issues)
  df = apply(df0, 2, as.numeric, as.character)
  
  nYrs = nrow(df)-1
  df.wy = matrix(NA, nrow = nYrs, ncol = 13)
  df.wy[,1] = as.numeric(as.character(df[-1,1]))
  colnames(df.wy) = c("wyears", 10:12, 1:9)
  
  i = 1
  for(i in 1:nYrs){
    #Oct-Dec
    df.wy[i,2:4] = df[i,11:13]
    #Jan-Sep
    df.wy[i,5:13] = df[(i+1),2:10]
  }
  
  df.wy = as.data.frame(df.wy)
  
  #subset to start and end year of flow record
  df.wy.sub = subset(df.wy, wyears >= min(stats$wyears) & wyears <= max(stats$wyears))
  
  return(df.wy.sub)
  
}

#############################################################################################################
#############################################################################################################
#############################################################################################################

### function to convert dataframes from long to wide for use in model as covariates
# df = pcp
# stats = stats
# yrs.df = 1906:2017
# type = "pcp"

longToWide = function(df, yrs.df, type, endYear){
  
  nyrs.df = length(yrs.df)  
  df.wy.mon = matrix(NA, nrow = nyrs.df, ncol = 13)
  df.wy.mon[,1] = yrs.df
  
  seq = seq(1, nrow(df), 12)
  i = 1
  j = 1
  for(i in 1:nyrs.df){
    df.wy.mon[i,2:13] = df[seq[j]:(seq[j]+11),2]
    j = j + 1
  }
  
  #post processing and conversion from mm to inches
  if(type == "pcp"){
    df.wy.mon[,-1] = df.wy.mon[,-1]/25.4
  }
  
  df.wy.mon = as.data.frame(df.wy.mon)
  colnames(df.wy.mon) = c("wyears", 10:12, 1:9)
  
  #subset to match year range of 1906-2017 (water years) and/or CESM-LE range of 
  df.wy.mon = subset(df.wy.mon, wyears >= 1921 & wyears <= endYear)
  
}

#############################################################################################################
#############################################################################################################
#############################################################################################################

#subset ESP data so only Oct-Sep water year format is selected
# startMonth = startMonths.y2[1]
# fcstMonth = fcstMonths.y2[1]
# leadTime = leadTimes.y2[1]
# year = 2

espProcessing = function(esp, startMonth, fcstMonth, leadTime, year, stats, model){
  
  df = NULL
  
  #subset ESP hindcasts for given lead time (represented by a certain forecast start month)
  espFcsts = subset(esp$locAll_fcst, format.Date(esp$locAll_fcst$Run.Date, "%m") == startMonth)
  
  #extract the selected starting month (Run Date) for each 5-year forecast in 2000-20XX hindcast period
  runDates = unique(espFcsts$Run.Date)
  
  #choose runDates that fall within the hindcast period
  #select appropriate water year depending on lead time
  if(year == 1){
    runDates = runDates[-c(1:(vs-1980-1))]
  } else if(year == 2){
    runDates = runDates[-c(1:(vs-1980-2))]
    runDates = head(runDates, -1)
  } 
  
  #loop thru runDates, with a sub loop on ESP traces for extracting spring flow forecasts
  i = 1
  for(i in 1:length(runDates)){
    
    runDate = runDates[i]
    
    dat.i = NULL
    
    #select i-th RunDate (Run Dates mark the beginning of the simulation period, with ~30 traces per RunDate and a simulation length of 5 years)
    df.i = subset(espFcsts, Run.Date == runDate)
    
    #select appropriate water year depending on lead time
    flowYear = as.numeric(format.Date(df.i$Timestep[(leadTime+1)], "%Y"))
    
    #extract TraceYears - each trace year is a different ensemble member and the Trace Year marks the begininning of the 5-year period from which precip and temp were taken to generate the ESP trace
    traceYears = data.frame(yr = as.numeric(as.character(unique(df.i$TraceYear))))
    #make ESP blind - drop any forecasts ahead of rundate
    traceYears = unlist(subset(traceYears, yr < flowYear-2 | yr > flowYear+2))
    
    #loop through each trace year (ensemble member)
    j = as.numeric(traceYears[1])
    for(j in traceYears){
      
      #subset for the j-th trace
      df.j = subset(df.i, TraceYear == j)
      
      #based on the selected lead time, extract the spring flow for this forecast period
      sp.q.j = data.frame(q.unreg = sum(df.j[(leadTime+1):(leadTime+1+3), 3:14]))
      
      #convert to naturalized and MAF
      sp.q.j = (sp.q.j*as.numeric(model$coefficients[2])+as.numeric(model$coefficients[1]))/1000
      
      #pull in data template 
      #tmp = data.frame(bdlm.fcsts.mod$year1$df.y1.dec[1,], row.names = NULL)
      tmp = NULL
      tmp$EnsMem = as.numeric(j)
      tmp$year = flowYear
      tmp$flow = as.numeric(sp.q.j)
      tmp$tag = "ESP"
      tmp$fcstYear = year
      tmp$fcstMonth = fcstMonth
      tmp$leadTime = leadTime
      tmp = data.frame(tmp)
      
      #calc flow terciles and assign label
      if(tmp$flow >= as.numeric(quantile(stats$q_maf, 2/3))){
        tmp$flowTercile = 3
        tmp$flowCategory = "High"
      } else if(tmp$flow <= as.numeric(quantile(stats$q_maf, 1/3))){
        tmp$flowTercile = 1
        tmp$flowCategory = "Low"
      }  else{
        tmp$flowTercile = 2
        tmp$flowCategory = "Average"
      }
      
      tmp$covariates = paste0("year.", year, "-", fcstMonth, ".fcst" )
      tmp$Observed = NA
      
      dat.i = rbind(dat.i, tmp)
      
    }
    
    #repeat for ensemble median
    tmp.med = dat.i[1,]
    tmp.med$EnsMem = NA
    tmp.med$flow = median(dat.i$flow)
    tmp.med$tag = "ESP.EnsembleMedian"
    tmp.med$flowTercile = NA
    tmp.med$flowCategory = NA
    tmp.med$Observed = as.numeric(subset(stats, wyears == flowYear)[3])
    
    #repeat for ensemble mean
    tmp.mean = dat.i[1,]
    tmp.mean$EnsMem = NA
    tmp.mean$flow = mean(dat.i$flow)
    tmp.mean$tag = "ESP.EnsembleMean"
    tmp.mean$flowTercile = NA
    tmp.mean$flowCategory = NA
    tmp.mean$Observed = as.numeric(subset(stats, wyears == flowYear)[3])
    
    df = rbind(df, dat.i, tmp.med, tmp.mean)
    
  }
  
  return(df)
  
}


#############################################################################################################
#############################################################################################################
#############################################################################################################

### read in all DPLE files (one file per each decadal forecast)

dple.import = function(pattern){
  
  dir = "K:/My Drive/Phd Research/CRB Midterm Temperature Perturbed Predictions/Data/Phase 1/CESM/CESM_DP_LE/monthly/monthly/quantile_UCO/"
  
  filenames <- list.files(dir, pattern = pattern, full.names=TRUE)
  
  ldf <- lapply(filenames, read.table, header = T)
  
  names = sapply(strsplit(filenames, split = "monthly/quantile_UCO/"), "[", 2)
  names = substr(names, 1, nchar(names)-4)
  names(ldf) <- names
  
  return(ldf)
}

#############################################################################################################
#############################################################################################################
#############################################################################################################

### process dple for different lead times
# dple.df = dple.tmax
# year = 2
# leadtime = 8
# tag = "tmax"

dp.le.processing = function(dple.df, dp.years, year, leadtime, tag){
  
  ndp = length(dp.years)
  dple = matrix(NA, nrow = ndp, ncol = 2)
  
  i = 1
  for(i in 1:ndp){
    
    dp.i = dple.df[[i]]
    
    if(year == 1){target.sp = c(6,9)}
    if(year == 2){target.sp = c(18,21)} 
    
    target.ind = (target.sp[1]-leadtime):target.sp[2]
    dp.i.sub = dp.i[target.ind,]
    
    dp.i.ensMean = as.numeric(rowMeans(dp.i.sub[,-1]))
    
    if(tag == "pcp"){
      #convert to in and sum monthly values
      dp.i.ensMean.agg = sum(dp.i.ensMean)/25.4
    }else{
      #convert to Celsius and calculate average monthly temperature
      dp.i.ensMean.agg = mean(dp.i.ensMean)-273.15
    }
    
    dple[i,1] = dp.years[i]+year
    dple[i,2] = dp.i.ensMean.agg    
    
  }
  
  #dple = data.frame(dple)
  colnames(dple) = c("year", paste0("dple.", tag))
  
  return(dple)
}


#############################################################################################################
#############################################################################################################
#############################################################################################################

# leadTimes = leadTimes.y1
# year = 1

dp.le.loop = function(leadTimes, year){
  
  nl = length(leadTimes)
  dp.list = vector("list", nl)
  
  dp.tags = c("pcp", "tmax", "tmin")
  nt = length(dp.tags)
  
  i=1
  for(i in 1:nl){
    
    li = leadTimes[i]
    cat(li)
    cat("\n")
    df.i = NULL
    
    j=1
    for(j in 1:nt){
      
      tj = dp.tags[j]
      cat(tj)
      cat("\n")
      
      if(tj == "pcp"){dp.df = dple.pcp}
      if(tj == "tmax"){dp.df = dple.tmax}
      if(tj == "tmin"){dp.df = dple.tmin}
      
      #execute function
      df.j = dp.le.processing(dp.df, dp.years, year, li, tj)
      
      df.i = cbind(df.i, df.j)
    }
    
    dp.list[[i]] = subset(data.frame(df.i[,-c(3,5)]), year >= 1983 & year <= 2017)
    
  }
  
  names(dp.list) = leadTimes
  
  return(dp.list)
}


#############################################################################################################
#############################################################################################################
#############################################################################################################

### NSE function (deprecated)
#calc NSE on a time series (model, observed), with user-defined climatology (single value)
nse = function(mod, obs, clim){
  
  nse = 1 - sum((mod-obs)^2)/sum((obs-clim)^2)
  
  return(nse)
  
}

#############################################################################################################
#############################################################################################################
#############################################################################################################

### BDLM forecast function

#select lead years to run
# df = df.y2.oct_18mo
# df = df.tmp
# #validation period start - first forecast is made in this year
# vs = 1983
# nsim = 500
# ar = F
# fcstYear = 2
# fcstMonth = "Oct"
# leadTime = 18

DLM.forecast = function(df, vs, nsim, ar, fcstYear, fcstMonth, leadTime){
  
  options(warnings = -1)
  
  #validation data frame  
  df.val = subset(df, wyears >= vs)
  
  #p = par(mfrow=c(2,5))
  fcst.df = NULL
  
  #create matrix to store lead year i forecasts made during validation period
  fcst = matrix(data = NA, ncol = nrow(df.val), nrow = nsim)  
  colnames(fcst) = df.val$wyears
  #create storage matrix for random forest forecasts
  n.tree = nsim
  fcst.rf = matrix(data = NA, ncol = nrow(df.val), nrow = n.tree)  
  colnames(fcst.rf) = df.val$wyears
  
  #also examine change in variance and linear model forecasts
  df.variance = matrix(NA, nrow = nrow(df.val), ncol = 3)
  df.lm = matrix(NA, nrow = nrow(df.val), ncol = 5)
  
  #initialize lists to:
  #1 - store optimal model for each year
  opt.model = list()
  #2 - store variable importance for each year of hindcast (models are re-fit as hindcast progresses in time)
  varImp = NULL
  
  #loop through years of validation period  
  j = 1
  for(j in 1:ncol(fcst)){
    
    #calibration initial data frame
    df.cal = subset(df, wyears > vs+j+1 | wyears < vs+j-3)
    
    #assign data for processing--------------------------------------
    preds = df.cal[,-c(1:2)]
    Y = df.cal$q
    
    #calc correlation between each covariate and predictand (flow) for reference-----------------------------
    if(j == 1){
      covar.correlations = apply(preds, 2, cor, Y)
      cat("\n")
      cat(paste0("Year ", fcstYear, " forecast - made on 01 ", fcstMonth, " ~~ ", leadTime, "-month lead time"))
      cat("\n")
      print("Correlation between flow during forecast period and each predictor during calibration period:")
      cat("\n")
      print(covar.correlations)
      cat("\n")
    }
    
    #create a dlm model----------------------------------------------
    
    #first fit linear model  
    polyfit = lm(q ~ ., data = df.cal[,-1])
    
    #optimize with AIC
    kp = log(ncol(df.cal)-2)
    polyfit.opt = stepAIC(polyfit, direction = "both", k = kp, trace = F)
    # if q~ 1 is best model, then revert to full model (former causes issues with BDLM fitting)
    if(length(polyfit.opt$terms[[3]]) < 3){
      polyfit.opt = polyfit
    }
    
    #record selected model
    opt.model = append(opt.model, polyfit.opt$terms)
    
    #revise matrix X of predictors to only contain predictors in optimal model
    X = as.matrix(polyfit.opt$model[,-1])
    
    #predict year j flow using the linear model
    lm.pred = predict(polyfit.opt, newdata = df.val[j,-c(1:2)], se.fit = T, interval = "prediction")
    
    #store linear model results separately for later comparison
    df.lm[j,1] = df.val$wyears[j]
    df.lm[j,2:4] = lm.pred$fit
    df.lm[j,5] = lm.pred$se.fit   
    
    #generate Random Forest forecast using full model -----------------------------------------------------------------------------
    
    #train RF
    rf.train = randomForest(q ~ ., data = df.cal[,-1], ntree = n.tree, importance = T)
    
    #create variable importance for RF
    vip.j = varImpPlot(rf.train, main = paste0("Year ", fcstYear, " forecast - made on 01 ", fcstMonth, " to predict ", df.val$wyears[j], " spring flow\n", leadTime, "-month lead time\n"), cex.main = 0.8)
    vip.jm = melt(vip.j)
    colnames(vip.jm)[1:2] = c("Covariate", "Metric")
    vip.jm$fcstYear = df.val$wyears[j]
    #store results with other hindcast years
    varImp = rbind(varImp, vip.jm)
    
    #predict ensemble using RF
    #rf.pred = predict(rf.train, df.val[j,-c(1:2)], predict.all=TRUE)
    #rf.pred.sub = sample(rf.pred$individual, size = nsim, replace = T)
    fcst.rf[,j] = as.numeric(predict(rf.train, newdata = df.val[j,-c(1:2)], predict.all=TRUE)[[2]])
    
    rm(rf.train) #remove to avoid overloading memory
    
    #loop through simulations
    #k = 1
    #for(k in 1:nsim){
    #rf.train = randomForest(x = df.cal[,-c(1:2)], y = df.cal[,2], ntree = 500)
    #fcst.rf[k,j] = predict(rf.train, newdata = df.val[j,-c(1:2)])
    #}
    
    #continue with BDLM --------------------------------------------------------------------------------------------
    np=ncol(X)+1
    
    residvar=var(polyfit.opt$resid)
    
    df.variance[j,1] = df.val$wyears[j]
    df.variance[j,2] = residvar
    
    #V = residvar #variance of the residual error
    V = 0.25 #custom value
    
    #r = factor corresponding to W/V when var(Xi)=var(Y)=1 for all i
    r = rep(0.25, ncol(X))
    W=r*V*c(1,1/diag(var(X))) #r=W/V, the signal to noise ratio when var(X)=1; this is now a vector of length np
    
    m0in=summary(polyfit.opt)$coefficients[,1]
    C0in=vcov(polyfit.opt, complete = T)
    
    #remove optimized lm model to reduce storage requirements
    rm(polyfit.opt)
    
    dlmod=dlmModReg(X,dV=V,dW=W,m0=m0in,C0=C0in)
    dlmodsmooth=dlmSmooth(Y,dlmod,debug=TRUE)
    
    dlmod.coefs = dlmodsmooth$s[-1,]
    #dlmod.coefs
    
    df.variance[j,3] = dlmod$V
    
    dlm.tail = tail(dlmod.coefs, 1)
    dlm.tail
    
    #-----------------------------------------------------------------------------------------------------------------
    #calculate modeled flow during fitting period (only do for first forecast period)
    if(j == 1){
      
      fit = as.vector(rowSums(cbind(dlmod.coefs[,1], dlmod.coefs[,2:np]*X)))
      
      plot(df.cal$wyears, df.cal$q, type = "l", xlab = "Water Year", ylab = "Flow (MAF)")
      lines(df.cal$wyears, fit, col = "red", lty = 3)
      
      fit.cor = cor(fit, df.cal$q)
      cat("\n")
      print("Correlation between actual and fitted flow during calibration period:")
      cat("\n")
      print(fit.cor)
      cat("\n")
      
      plot(fit, df.cal$q)
      
    }
    
    
    ########################################################################################
    #calc posterior
    #Eqn 2.4 from Dynamics Linear Models by Petris
    
    #Yt = Ft*theta.t + vt, vt ~ N(0,Vt)
    #theta.t = Gt*theta.t-1 + wt, wt ~ N(0,Wt)
    
    covs = c("Intercept", paste0(colnames(X), " coefficient"))
    
    # #compare fitted theta.t with theta.t posterior simulated from theta.t-1 mean and variance
    # #do separately for intercept and each coef
    # par(mfrow=c(1,np), oma = c(1,1,3,1), xpd = F)
    # posterior.j = matrix(NA, nrow = nsim, ncol = np)
    # 
    # #loop thru simulations of coef
    # k = 1 
    # for(k in 1:np){
    #   
    #   #generate state eqn posterior for each year in hindcast period based on past year state and variance v
    #   #previous year's (j-1) theta
    #   theta.t1 = tail(dlmod.coefs, 2)[1,k]
    #   #variance for k-th (current) coefficient
    #   Wt = dlmod$W[k,k]
    #   #initialize matrix to store current year's (j-th) theta 
    #   theta.t2 = matrix(NA, nrow = nsim, ncol = 1)
    #   
    #   #gen random value
    #   l = 1
    #   for(l in 1:nsim){
    #     set.seed(l)
    #     theta.t2[l] = rnorm(1, mean = theta.t1, sd = sqrt(Wt))
    #     #theta.t2[l] = theta.t1+rnorm(1, 0, sqrt(Wt))
    #   }
    #   
    # 
    #   hist(theta.t2, ylab = "Count", xlab = covs[k], main = NULL)
    #   abline(v = dlm.tail[k], col = "red", lwd = 2)
    # 
    #   posterior.j[,k] = theta.t2
    #   
    # }
    # mtext(paste0("Posterior and mean (fitted) coefficient for ", tail(dfi$year, 1)), side = 3, line = 2, at = -4, font.lab = 2)
    
    ################################################################################################################
    #simulate next year's (j+1-th) theta from DLM fitted mean of current year's (j-th) theta and use to generate flow prediction ensemble for forecast period
    covs.j1 = df.val[j, -c(1:2)]
    
    #select only predictors from optimal model
    covs.j1 = covs.j1[names(covs.j1) %in% colnames(X)]
    
    #initialize storage
    posterior.j1 = matrix(NA, nrow = nsim, ncol = np)
    
    #option to use AR model to predict mean theta j+1 instead of using theta j (from Eqn 2.4)
    if(ar == T){
      theta.j1 = matrix(NA, nrow = np, ncol = 1)
      
      # par(mfrow=c(1,np), oma = c(2,1,3,1))
      # l = 1
      # for(l in 1:np){
      #   acf(dlmod.coefs[,l], main = covs[l])
      # }
      # 
      # par(mfrow=c(1,np), oma = c(2,1,3,1))
      # l = 1
      # for(l in 1:np){
      #   pacf(dlmod.coefs[,l], main = covs[l])
      # }
      
      l = 1
      for(l in 1:np){
        #use either AR or ARIMA (with order determined from acf and pacf)
        #ar.lj = arima(dlmod.coefs[,l], order = c(2,0,5), method = "ML")
        ar.lj = ar(dlmod.coefs[,l])
        p = predict(ar.lj, nahead = 1) 
        theta.j1[l] = p$pred[1]
      }
      
    }
    
    #loop through simulations
    k = 1
    for(k in 1:nsim){
      
      #calculate random sample from year j (e.g. 1999) posterior dist for each coef to create random year j+1 (e.g. 2000) coef, then pair with covariates for year j+1 (which are past values of PDO, ENSO, AMO, flow -> so these are values from year j or j-1)
      
      coefs.j1 = matrix(NA, nrow = np, ncol = 1)
      
      #randomly sample variance from for each coef (use the same prob for all coefs so the regime is similar)
      
      if(ar == T){
        
        l = 1
        for(l in 1:np){
          xmu = theta.j1[l]
          #set.seed(l*k)
          coefs.j1[l] = rnorm(1, mean = xmu, sd = sqrt(dlmod$W[l,l]))
        }
        
      } else {
        
        l = 1
        for(l in 1:np){
          #set.seed(l*k)
          xmu = tail(dlmod.coefs, 1)[l]
          coefs.j1[l] = rnorm(1, mean = xmu, sd = sqrt(dlmod$W[l,l]))
        }
        
      }
      
      #store generated year j+1 posterior dist for later comparison with prior year's posterior dist
      posterior.j1[k,] = coefs.j1 
      
      #multiplty the coefs generated by the covariates for forecast year to estimate mean flow (e.g. for forecasting year 2000 flow, use observed flow, climate indices, etc. from 1999)
      xmu = sum(cbind(coefs.j1[1], coefs.j1[-1]*covs.j1))
      
      #resample mean flow using either measurement variance or variance of spring flows along with forecasted mean flow (variance of spg flows will give bigger range)
      #flow.j1 = rnorm(1, mean = xmu, sd = sqrt(var(df.cal$q)))
      flow.j1 = rnorm(1, mean = xmu, sd = sqrt(dlmod$V))
      
      #fcst[k,j] = xmu
      fcst[k,j] = flow.j1
      
    }
    
    
    # #compare posterior distributions for year's j+1 and j
    # par(mfrow=c(1,np), oma = c(2,1,3,1), xpd = NA)
    # 
    # #set number of values to generate for each coef
    # #loop thru simulations of coef
    # k = 1 
    # for(k in 1:np){
    #   hist(posterior.j[,k], ylab = "Count", xlab = covs[k], main = NULL, col=rgb(0,0,1,1/4),)
    #   hist(posterior.j1[,k], col=rgb(1,0,0,1/4), add = T)
    # }
    # 
    # legend(-8.5, -130, ncol=2, c(paste0(vs+j-2), paste0(vs+j-1)), fill=c("blue","red"), bty = 'n', cex = 1.5)
    # mtext("Posterior distributions for coefficients for years 1 and 2", side = 3, line = 2, at = -4, font.lab = 2)
    
  }
  
  #add lead time tag to variable importance DF
  varImp$leadTime = leadTime
  
  #plot aggregated variable importance for RF models
  p1 = ggplot(subset(varImp, Metric == "%IncMSE"), aes(x = reorder(Covariate, value), y = value)) + 
    geom_boxplot() + theme_bw() + coord_flip() +
    theme(axis.title = element_text(face = "bold")) + xlab("Covariate") + ylab("Increase in MSE if variable is permuted") +
    #ggtitle(paste0('Aggregated variable importance from all models trained during hindcast\n', leadTime, "-month leadtime")) +
    geom_hline(yintercept = 0) 
  
  #print(p1)
  
  p2 = ggplot(subset(varImp, Metric == "IncNodePurity"), aes(x = reorder(Covariate, value), y = value)) + 
    geom_boxplot() + theme_bw() + coord_flip() +
    theme(axis.title = element_text(face = "bold")) + xlab("Covariate") + ylab("Increase in node purity") +
    #ggtitle(paste0('Aggregated variable importance from all models trained during hindcast\n', leadTime, "-month leadtime")) +
    geom_hline(yintercept = 0) 
  
  #print(p2)
  
  p3 = grid.arrange(p1, p2, ncol = 2, top = paste0('Aggregated variable importance from all models trained during hindcast\n', leadTime, "-month leadtime"))
  
  print(p3)
  
  ###################################################################################################
  #process forecasted data - BDLM
  fcst.melt0 = melt(fcst)
  colnames(fcst.melt0) = c("EnsMem", "year", "flow")
  fcst.melt0$tag = "DLM"
  fcst.melt0$fcstYear = fcstYear
  fcst.melt0$fcstMonth = fcstMonth
  fcst.melt0$leadTime = leadTime
  
  #process forecasted data - random forest
  fcst.rf.melt0 = melt(fcst.rf)
  colnames(fcst.rf.melt0) = c("EnsMem", "year", "flow")
  fcst.rf.melt0$tag = "RF"
  fcst.rf.melt0$fcstYear = fcstYear
  fcst.rf.melt0$fcstMonth = fcstMonth
  fcst.rf.melt0$leadTime = leadTime
  
  #optionally keep IQR (or custom range) only
  constrainFlow = T
  if(constrainFlow == T){
    fcst.melt01 = NULL
    j = 1
    for(j in 1:nrow(df.val)){
      
      df.sub = subset(fcst.melt0, year == df.val$wyears[j])
      
      # q3 = quantile(df.sub$flow, 0.95)
      # q1 = quantile(df.sub$flow, 0.05)
      
      q3 = max(df$q)
      q1 = min(df$q)
      
      df.sub1 = subset(df.sub, flow <= q3 & flow >= q1)
      
      fcst.melt01 = rbind(fcst.melt01, df.sub1)
      
    }
    
    fcst.df = rbind(fcst.df, fcst.melt01)
    
  } else{
    
    fcst.df = rbind(fcst.df, fcst.melt0)
  }
  
  #append observed flows for plotting ---------------------------------------------------------------------------------------------------
  obs = data.frame(EnsMem = NA, year = df.val[,1], flow = df.val$q, tag = "Observed", fcstYear = NA, fcstMonth = NA, leadTime = NA)
  
  
  #add linear model results (mean forecast and 95% prediction interval) -------------------------------------------------------------------
  lm.fit = data.frame(EnsMem = NA, year = df.val[,1], flow = df.lm[,2], tag = "LM_Mean", fcstYear = fcstYear, fcstMonth = fcstMonth, leadTime = leadTime)
  lm.lwr = data.frame(EnsMem = NA, year = df.val[,1], flow = df.lm[,3], tag = "LM_Lower", fcstYear = fcstYear, fcstMonth = fcstMonth, leadTime = leadTime)
  lm.upr = data.frame(EnsMem = NA, year = df.val[,1], flow = df.lm[,4], tag = "LM_Upper", fcstYear = fcstYear, fcstMonth = fcstMonth, leadTime = leadTime)
  
  #merge--------------------------------------------------
  fcst.melt = rbind(fcst.df, fcst.rf.melt0, lm.fit, lm.lwr, lm.upr, obs)
  
  # ### NSE
  # nse.DLM = nse(mod = subset(fcst.melt, tag == "EnsembleMean.DLM")[,3], obs = subset(fcst.melt, tag == "Observed")[,3], clim = clim)
  # 
  # cat("\n")
  # print("Ensemble mean NSE:")
  # cat("\n")
  # print(nse.DLM)
  # cat("\n")
  
  #calc terciles ----------------------------------------------------------------------------------------------------------
  fcst.melt$flowTercile = NA
  fcst.melt$flowCategory = NA
  
  i = 1
  for(i in 1:nrow(fcst.melt)){
    
    #calc flow terciles and assign label
    if(fcst.melt$flow[i] >= as.numeric(quantile(stats$q_maf, 2/3))){
      fcst.melt$flowTercile[i] = 3
      fcst.melt$flowCategory[i] = "High"
    } else if(fcst.melt$flow[i] <= as.numeric(quantile(stats$q_maf, 1/3))){
      fcst.melt$flowTercile[i] = 1
      fcst.melt$flowCategory[i] = "Low"
    } else{
      fcst.melt$flowTercile[i] = 2
      fcst.melt$flowCategory[i] = "Average"
    }
    
  }
  
  
  #remove negative values
  fcst.melt = subset(fcst.melt, flow > 0)
  
  #add covariate tag
  fcst.melt$covariates = paste0("year.", fcstYear, "-", fcstMonth, ".fcst")
  
  # #plot variance over time-----------------------------------------------------------------------------------
  #   plot(x = df.variance[,1], y = df.variance[,2], type = "l", main = "LM residual variance over time")
  #   plot(x = df.variance[,1], y = df.variance[,3], type = "l", main = "Residual variance used in DLM over time")
  # 
  # #plot lm reuslts
  #   plot(x = df.lm[,1], y = df.lm[,2], type = "l", ylim = c(0,20), main = "Linear model flow forecasts")
  #   lines(x = df.lm[,1], y = df.lm[,3], col = "red")
  #   lines(x = df.lm[,1], y = df.lm[,4], col = "red")
  #   points(df.val$wyears, df.val$q)
  # 
  # 
  #   plot(x = df.lm[,1], y = df.lm[,5], type = "l", main = "LM standard error over time")
  
  
  #post-process list of optimized models for each forecasted year
  names(opt.model) = df.val$wyears
  
  #return products
  out = list(fcst.melt, opt.model, varImp)
  names(out) = c("forecasts", "optimal.models", "variable.importance")
  
  return(out)
  
}

#############################################################################################################
#############################################################################################################
#############################################################################################################

#########################################################################################################
### Function to try various models (each model is a different lead time)-------------------------------

# df.mod = models.y2
# fcstYear = 2
# fcstMonths = fcstMonths.y2
# leadTimes = leadTimes.y2
# vs = 1983

forecastLoop = function(df.mod, fcstYear, fcstMonths, leadTimes, vs){
  
  nsim = 500
  
  n = length(df.mod)
  df.fcsts = vector("list", n)
  df.optModels = vector("list", n)
  df.varImp = NULL
  
  i = 1
  for(i in 1:n){
    
    cat("Forecast year and month:\n")
    cat(names(df.mod[i]))
    cat("\n")
    
    df.tmp = df.mod[[i]]
    
    df.fcst.i = DLM.forecast(df.tmp, vs, nsim = nsim, ar = F, fcstYear = fcstYear, fcstMonth = fcstMonths[i], leadTime = leadTimes[i]) 
    
    df.fcsts[[i]] = df.fcst.i$forecasts
    names(df.fcsts)[i] = names(df.mod[i])
    
    df.optModels[[i]] = df.fcst.i$optimal.models
    names(df.optModels)[i] = names(df.mod[i])
    
    df.varImp = rbind(df.varImp, df.fcst.i$variable.importance)
    
  }
  
  out = list(df.fcsts, df.optModels, df.varImp)
  names(out) = c("forecasts", "optimal.models", "variable.importance")
  
  return(out)
  
}

#############################################################################################################
#############################################################################################################
#############################################################################################################

#-----------------------------------------------------------------------------------------------------------
### Plot ensemble median (equal to ensemble mean since BDLM ensemble is normally distributed)
#function to calculate ensemble median and append to list of model hindcasts

# list = bdlm.fcsts

CalcEnsMedian = function(list, fcstTag){
  
  n = length(list)
  list.mod = lapply(list, lapply, cbind, Observed = NA)
  
  i = 1
  for(i in 1:n){
    
    l.i = list.mod[[i]]
    m = length(l.i)
    
    j = 1
    for(j in 1:m){
      
      df.j = l.i[[j]]
      
      yrs = unique(df.j$year)
      
      k = yrs[1]
      for(k in yrs){
        
        df.k = subset(df.j, tag == fcstTag & year == k)
        
        dat.k = df.k[1,]
        dat.k[c(1,8:9)] = NA
        dat.k$tag = paste0(fcstTag, "_Median")
        dat.k$flow = median(df.k$flow)
        dat.k$Observed = subset(df.j, tag == "Observed" & year == k)[3]
        
        list.mod[[i]][[j]] = rbind(list.mod[[i]][[j]], dat.k)
        
      }
      
    }
    
  }
  
  
  
  return(list.mod)
  
}

#############################################################################################################
#############################################################################################################
#############################################################################################################

#CRPSS function
###############################################################################
#calc CRPSS on terciles

# fcst = bdlm.fcsts$year1[[1]]
# fcstTag = "DLM"

# fcst = esp.fcsts$year1[[1]]
# #fcst = esp.fcsts$year2[[1]]
# fcstTag = "ESP"

crpss = function(fcst, fcstTag, stats, plot){
  
  fcst = subset(fcst, tag == fcstTag)
  
  #if using ESP, make the record match the obs flow series  
  if(fcst$tag[1] == "ESP"){
    fcst = subset(fcst, year <= max(stats$wyears))
  }
  
  #transform data into correct format for EnsRps function
  years = unique(fcst$year)
  nYrs = length(years)
  df.crpss = NULL
  flowCat = NULL
  
  i = 1
  for(i in 1:nYrs){
    
    df.i = subset(fcst, year == years[i])
    
    #if using ESP, drop the ESP trace year that is the same year of the current skill calculation
    if(fcst$tag[1] == "ESP"){
      df.i = subset(df.i, EnsMem != years[i])
      if(df.i$fcstYear[1] == 2){
        df.i = subset(df.i, EnsMem != years[i]-1)
      }
    }
    
    mat.fcst = as.matrix(t(df.i$flow))
    
    # clim = subset(esp.fcsts.all, tag == "ESP" & year == df.i$year[1] & leadTime == df.i$leadTime[1])
    # mat.clim = as.matrix(t(clim$flow))
    #mat.clim = as.matrix(t(subset(stats, wyears < years[i])[,3]))
    mat.clim = as.matrix(t(subset(stats, wyears != years[i])[,3]))
    
    obs = subset(stats, wyears == years[i])[,3]
    
    #calc RPS time series (one score per year) for forecast and clim, then calc RPSS from the two scores
    crps.f = EnsCrps(mat.fcst, obs)
    crps.c = EnsCrps(mat.clim, obs)
    crpss.f = 1 - crps.f/crps.c
    
    df.crpss = rbind(df.crpss, crpss.f)
    
    flowCat = rbind(flowCat, subset(stats, wyears == years[i])[,7])
    
  }
  
  df.crpss = as.data.frame(df.crpss)
  
  #optional plotting
  if(plot == T){
    boxplot(df.crpss, ylab = "CRPSS")
    abline(h = 0, col = "red")
  }
  
  df.crpss$fcstYear = fcst$fcstYear[1]
  df.crpss$fcstMonth = fcst$fcstMonth[1]
  df.crpss$leadTime = fcst$leadTime[1]
  df.crpss$covariate = fcst$covariates[1]
  df.crpss$metric = "CRPSS"
  if(fcst$tag[1] == "ESP"){
    df.crpss$fcstType = "ESP"
  } else if(fcst$tag[1] == "DLMEnsemble"){
    df.crpss$fcstType = "BDLM"
  } else{
    df.crpss$fcstType = "RF"
  }
  
  df.crpss$flowCategory = flowCat
  
  return(df.crpss)
  
  
}

#############################################################################################################
#############################################################################################################
#############################################################################################################

#Tercile RPSS function
###############################################################################
#calc RPSS on terciles

#fcst = df2.forecast.nl
# plot = T

rpss = function(fcst, fcstTag, stats, plot){
  
  fcst = subset(fcst, tag == fcstTag)
  
  #if using ESP, make the record match the obs flow series
  if(fcst$tag[1] == "ESP"){
    fcst = subset(fcst, year <= max(stats$wyears))
  }
  
  #transform data into correct format for EnsRps function
  years = unique(fcst$year)
  nYrs = length(years)
  df.rpss = NULL
  flowCat = NULL
  
  i = 1
  for(i in 1:nYrs){
    
    df.i = subset(fcst, year == years[i])
    
    #if using ESP, drop the ESP trace year that is the same year of the current skill calculation
    if(fcst$tag[1] == "ESP"){
      df.i = subset(df.i, EnsMem != years[i])
    }
    
    mat.fcst = as.matrix(t(df.i$flowTercile))
    
    # clim = subset(esp.fcsts.all, tag == "ESP" & year == df.i$year[1] & leadTime == df.i$leadTime[1])
    # mat.clim = as.matrix(t(clim$flowTercile))
    #mat.clim = as.matrix(t(subset(stats, wyears < years[i])[,6]))
    mat.clim = as.matrix(t(subset(stats, wyears != years[i])[,6]))
    
    obs = subset(stats, wyears == years[i])[,6]
    
    #calc RPS time series (one score per year) for forecast and clim, then calc RPSS from the two scores
    rps.f = EnsRps(mat.fcst, obs)
    rps.c = EnsRps(mat.clim, obs)
    rpss.f = 1 - rps.f/rps.c
    
    df.rpss = rbind(df.rpss, rpss.f)
    
    flowCat = rbind(flowCat, subset(stats, wyears == years[i])[,7])
    
    
  }
  
  df.rpss = as.data.frame(df.rpss)
  
  #optional plotting
  # if(plot == T){
  #   boxplot(df.rpss, ylab = "RPSS")
  #   abline(h = 0, col = "red")
  # }
  
  df.rpss$fcstYear = fcst$fcstYear[1]
  df.rpss$fcstMonth = fcst$fcstMonth[1]
  df.rpss$leadTime = fcst$leadTime[1]
  df.rpss$covariate = fcst$covariates[1]
  df.rpss$metric = "RPSS"
  if(fcst$tag[1] == "ESP"){
    df.rpss$fcstType = "ESP"
  } else if(fcst$tag[1] == "DLMEnsemble"){
    df.rpss$fcstType = "BDLM"
  } else{
    df.rpss$fcstType = "RF"
  }
  
  df.rpss$flowCategory = flowCat
  
  return(df.rpss)
  
}

#############################################################################################################
#############################################################################################################
#############################################################################################################

### plot forecast time series function

### plot forecast-----------------------------------------------

plot.single = function(df, title, fcstTag){
  ggplot(data = subset(df, tag == fcstTag),
         aes(x = year, y = flow, group = year, color = tag)) +
    geom_boxplot() +
    geom_point(data = subset(df, tag == "Observed")) +
    xlab("Year") + ylab("Flow (MAF)") +
    theme(axis.title = element_text(face = "bold")) +
    ggtitle(title)
  #coord_cartesian(ylim = c(0, 100))
}

#############################################################################################################
#############################################################################################################
#############################################################################################################

# list = esp.fcsts$year1
# # list = bdlm.fcsts[[1]]
# year = 1
# plot = F
# obsDat = stats
# espClim = esp.fcsts.all
# fcstTag = "ESP"

postProcessing = function(list, fcstTag, obsDat, year, plot){
  
  n = length(list)
  crpss.list = vector("list", n)
  rpss.list = vector("list", n)
  
  # i = 1
  # fcst = list[[i]]
  # fcstTag = fcstTag
  # stats = obsDat
  # plot = plot
  
  for(i in 1:n){
    
    title = list[[i]]$covariates[1]
    print(plot.single(list[[i]], title, fcstTag))
    crpss.list[[i]] = crpss(list[[i]], fcstTag, obsDat, plot)
    rpss.list[[i]] = rpss(fcst = list[[i]], fcstTag = fcstTag, stats = obsDat, plot = plot)
    
  }
  
  out = list(crpss.list, rpss.list)
  names(out) = c("CRPSS", "RPSS")
  
  return(out)
  
}

#############################################################################################################
#############################################################################################################
#############################################################################################################

# postProcessing = function(list, fcstTag, obsDat, espClim, year, plot){
#   
#   n = length(list)
#   crpss.list = vector("list", n)
#   rpss.list = vector("list", n)
#   
#   i = 1
#   for(i in 1:n){
#     
#     title = list[[i]]$covariates[1]
#     print(plot.single(list[[i]], title, fcstTag))
#     crpss.list[[i]] = crpss(list[[i]], fcstTag, obsDat, espClim, plot)
#     rpss.list[[i]] = rpss(list[[i]], fcstTag, obsDat, espClim, plot)
#     
#   }
#   
#   out = list(crpss.list, rpss.list)
#   names(out) = c("CRPSS", "RPSS")
#   
#   return(out)
#   
# }

#############################################################################################################
#############################################################################################################
#############################################################################################################
