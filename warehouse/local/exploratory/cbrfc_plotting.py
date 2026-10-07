import matplotlib.pyplot as plt


def plot_seasonal_wsup_qc(
    location_id,
    obs_df,
    sim_df,
    plot_start,
    variable_name=None,
):
    kaf_to_cubic_meters = 1000 * 1233.48184
    esp_members = ["p10", "p50", "p90"]
    official_members = ["crx", "c30", "cmp", "c70", "crn"]

    plot_sim_df = sim_df.loc[sim_df["location_id"].eq(location_id)].copy()
    plot_obs_df = obs_df.loc[obs_df["location_id"].eq(location_id)].copy()

    available_variables = plot_sim_df["variable_name"].dropna().unique()
    if variable_name is None:
        if len(available_variables) != 1:
            raise ValueError(
                f"Expected one variable for {location_id}; found "
                f"{list(available_variables)}. Specify variable_name."
            )
        variable_name = available_variables[0]

    plot_sim_df = plot_sim_df.loc[
        plot_sim_df["variable_name"].eq(variable_name)
    ].copy()
    plot_obs_df = plot_obs_df.loc[
        plot_obs_df["variable_name"].eq(variable_name)
    ].copy()

    if plot_sim_df.empty:
        raise ValueError(
            f"No simulated data found for {location_id} and {variable_name}"
        )

    for frame in (plot_sim_df, plot_obs_df):
        frame["reference_time"] = pd.to_datetime(frame["reference_time"])
        frame["value"] = frame["value"] / kaf_to_cubic_meters

    esp = plot_sim_df.loc[plot_sim_df["member"].isin(esp_members)]
    esp_wide = esp.pivot_table(
        index="reference_time",
        columns="member",
        values="value",
        aggfunc="first",
    ).sort_index()

    official = plot_sim_df.loc[
        plot_sim_df["member"].isin(official_members)
    ].copy()
    official_wide = official.pivot_table(
        index="reference_time",
        columns="member",
        values="value",
        aggfunc="first",
    ).sort_index()

    fig, ax = plt.subplots(figsize=(11, 6))

    if {"p10", "p90"}.issubset(esp_wide.columns):
        ax.fill_between(
            esp_wide.index,
            esp_wide["p10"],
            esp_wide["p90"],
            color="tab:blue",
            alpha=0.15,
            label="ESP p10-p90",
        )

    if "p50" in esp_wide.columns:
        ax.plot(
            esp_wide.index,
            esp_wide["p50"],
            color="tab:blue",
            linewidth=2,
            label="ESP p50",
        )

    if "cmp" in official_wide.columns:
        available_official_members = [
            member
            for member in official_members
            if member in official_wide.columns
        ]
        whiskers = official_wide.loc[
            official_wide["cmp"].notna()
            & official_wide[available_official_members].count(axis=1).gt(1)
        ].copy()

        if not whiskers.empty:
            whiskers["low"] = whiskers[available_official_members].min(axis=1)
            whiskers["high"] = whiskers[available_official_members].max(axis=1)
            lower_error = (whiskers["cmp"] - whiskers["low"]).clip(lower=0)
            upper_error = (whiskers["high"] - whiskers["cmp"]).clip(lower=0)

            ax.errorbar(
                whiskers.index,
                whiskers["cmp"],
                yerr=[lower_error, upper_error],
                fmt="o",
                color="deeppink",
                ecolor="hotpink",
                elinewidth=1.5,
                capsize=4,
                markersize=5,
                alpha=0.85,
                label="Official cmp and range",
            )

    official_components = official.loc[official["member"].ne("cmp")]
    if not official_components.empty:
        ax.scatter(
            official_components["reference_time"],
            official_components["value"],
            marker="_",
            color="deeppink",
            s=180,
            linewidths=1.5,
            alpha=0.85,
            label="Official components",
        )

    if not plot_obs_df.empty:
        obs = plot_obs_df.sort_values("reference_time")
        ax.plot(
            obs["reference_time"],
            obs["value"],
            color="tab:red",
            linewidth=2,
            label="Observed",
        )

    ax.set_xlim(left=plot_start)
    ax.set_title(f"CBRFC seasonal WSV QC: {location_id} ({variable_name})")
    ax.set_xlabel("Forecast reference time")
    ax.set_ylabel("Water supply volume (kaf)")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    plt.show()