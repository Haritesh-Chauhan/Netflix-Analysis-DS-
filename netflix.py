import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import requests

# ----------------------------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Netflix Content Analysis",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------------------------------------------------------
# STYLING
# ----------------------------------------------------------------------------
st.markdown(
    """
    <style>
        .main { background-color: #0e1117; }
        div[data-testid="stMetric"] {
            background-color: #1c1f26;
            border: 1px solid #2b2f3a;
            border-radius: 10px;
            padding: 14px 10px 6px 10px;
        }
        div[data-testid="stMetricLabel"] { color: #b3b3b3; }
        h1, h2, h3 { color: #e50914; }
        .stTabs [data-baseweb="tab"] { font-size: 15px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# DATA LOADING & CLEANING
# ----------------------------------------------------------------------------
@st.cache_data
def load_data(path="netflix_titles.csv"):
    df = pd.read_csv(path)

    # Dates
    df["date_added"] = pd.to_datetime(df["date_added"].str.strip(), format="mixed", errors="coerce")
    df["year_added"] = df["date_added"].dt.year
    df["month_added"] = df["date_added"].dt.month_name()

    # Fill missing categoricals (keep director/cast as-is for the search tab,
    # just fill with a friendly placeholder so display doesn't show "nan")
    df["country"] = df["country"].fillna("Not Defined")
    df["director"] = df["director"].fillna("Not Available")
    df["cast"] = df["cast"].fillna("Not Available")

    # --- Data quality fix: a handful of rows have the duration value sitting in
    # the "rating" column (e.g. rating="74 min", duration=NaN) due to a known
    # bug in how this dataset was originally compiled. Move it back to duration
    # so the ratings dropdown only shows real ratings.
    bad_rating_mask = df["rating"].str.contains(r"^\d+\s*min$", na=False)
    df.loc[bad_rating_mask, "duration"] = df.loc[bad_rating_mask, "rating"]
    df.loc[bad_rating_mask, "rating"] = np.nan
    df["rating"] = df["rating"].fillna("Not Rated")

    # --- Duration: split correctly by type instead of blending minutes & seasons ---
    df["duration"] = df["duration"].fillna(df["duration"].mode()[0])
    duration_num = df["duration"].str.extract(r"(\d+)").astype(float)[0]
    df["duration_minutes"] = np.where(df["type"] == "Movie", duration_num, np.nan)
    df["duration_seasons"] = np.where(df["type"] == "TV Show", duration_num, np.nan)

    # Genres & countries: split into lists for multi-value analysis
    df["listed_in"] = df["listed_in"].fillna("Not Defined")
    df["genre_list"] = df["listed_in"].apply(lambda x: [g.strip() for g in x.split(",")])
    df["primary_genre"] = df["genre_list"].apply(lambda x: x[0])

    df["country_list"] = df["country"].apply(lambda x: [c.strip() for c in x.split(",")])
    df["primary_country"] = df["country_list"].apply(lambda x: x[0])

    return df


df = load_data()

# ----------------------------------------------------------------------------
# TMDb HELPER (optional — only used if the user supplies their own API key)
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def fetch_tmdb_details(title, api_key):
    """Look up a title on TMDb for poster, backdrop, and trailer.

    Returns a dict {poster_url, backdrop_url, trailer_url} or None on any failure.
    Everything here is best-effort: any missing piece is simply left as None
    rather than failing the whole lookup.
    """
    try:
        search_url = "https://api.themoviedb.org/3/search/multi"
        resp = requests.get(search_url, params={"api_key": api_key, "query": title}, timeout=6)
        resp.raise_for_status()
        results = [r for r in resp.json().get("results", []) if r.get("media_type") in ("movie", "tv")]
        if not results:
            return None
        top = results[0]
        media_type = top["media_type"]
        tmdb_id = top["id"]

        poster_url = f"https://image.tmdb.org/t/p/w500{top['poster_path']}" if top.get("poster_path") else None
        backdrop_url = (
            f"https://image.tmdb.org/t/p/w780{top['backdrop_path']}" if top.get("backdrop_path") else None
        )

        trailer_url = None
        try:
            vid_resp = requests.get(
                f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/videos",
                params={"api_key": api_key}, timeout=6,
            )
            vid_resp.raise_for_status()
            videos = vid_resp.json().get("results", [])
            trailer = next(
                (v for v in videos if v.get("site") == "YouTube" and v.get("type") == "Trailer"), None
            )
            if trailer:
                trailer_url = f"https://www.youtube.com/watch?v={trailer['key']}"
        except Exception:
            pass

        if not (poster_url or backdrop_url or trailer_url):
            return None
        return {"poster_url": poster_url, "backdrop_url": backdrop_url, "trailer_url": trailer_url}
    except Exception:
        return None


# ----------------------------------------------------------------------------
# SIDEBAR FILTERS
# ----------------------------------------------------------------------------
st.sidebar.image(
    "https://upload.wikimedia.org/wikipedia/commons/0/08/Netflix_2015_logo.svg",
    width=150,
)
st.sidebar.header("Filters")

content_type = st.sidebar.multiselect(
    "Content Type",
    options=sorted(df["type"].dropna().unique()),
    default=sorted(df["type"].dropna().unique()),
)

YEAR_OPTIONS = list(range(2008, 2023))
year_filter = st.sidebar.multiselect(
    "Release Year", options=YEAR_OPTIONS, default=YEAR_OPTIONS,
    help="Netflix titles in this dataset run from 2008 up to 2021 for release year; "
         "2022 is included here for completeness but currently has no matching titles.",
)

all_genres = sorted(set(g for sub in df["genre_list"] for g in sub))
genre_filter = st.sidebar.multiselect("Genre", options=all_genres, default=[])

all_countries = sorted(set(c for sub in df["country_list"] for c in sub if c != "Not Defined"))
country_filter = st.sidebar.multiselect("Country", options=all_countries, default=[])

rating_filter = st.sidebar.multiselect("Rating", options=sorted(df["rating"].unique()), default=[])

st.sidebar.markdown("---")
with st.sidebar.expander("🎬 TMDb poster lookup (optional)"):
    st.caption(
        "Add a free TMDb API key to show movie posters in the Search tab. "
        "Descriptions, ratings, and genres always come from the dataset — no key needed for those."
    )
    tmdb_api_key = st.text_input("TMDb API Key", type="password")

st.sidebar.markdown("---")
st.sidebar.caption(f"Dataset: {len(df):,} titles total")

# ----------------------------------------------------------------------------
# APPLY FILTERS (used by every tab except Search)
# ----------------------------------------------------------------------------
mask = df["type"].isin(content_type) & df["release_year"].isin(year_filter)
if genre_filter:
    mask &= df["genre_list"].apply(lambda gl: any(g in gl for g in genre_filter))
if country_filter:
    mask &= df["country_list"].apply(lambda cl: any(c in cl for c in country_filter))
if rating_filter:
    mask &= df["rating"].isin(rating_filter)

fdf = df[mask].copy()

# ----------------------------------------------------------------------------
# HEADER
# ----------------------------------------------------------------------------
st.title("🎬 Netflix Content Analysis Dashboard")
st.caption("Explore Netflix's global catalog: content mix, genres, countries, and growth over time.")

if fdf.empty:
    st.warning("No titles match the current filters. Try widening your selection in the sidebar.")
    st.stop()

# ----------------------------------------------------------------------------
# KPI ROW
# ----------------------------------------------------------------------------
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total Titles", f"{len(fdf):,}")
k2.metric("Movies", f"{(fdf['type'] == 'Movie').sum():,}")
k3.metric("TV Shows", f"{(fdf['type'] == 'TV Show').sum():,}")
n_countries = len(set(c for sub in fdf["country_list"] for c in sub if c != "Not Defined"))
k4.metric("Countries", f"{n_countries:,}")
avg_movie_len = fdf.loc[fdf["type"] == "Movie", "duration_minutes"].mean()
k5.metric("Avg Movie Duration", f"{avg_movie_len:.0f} min" if pd.notna(avg_movie_len) else "N/A")
top_rating = fdf["rating"].mode()[0] if not fdf["rating"].mode().empty else "N/A"
k6.metric("Most Common Rating", top_rating)

st.markdown("---")

# ----------------------------------------------------------------------------
# TABS
# ----------------------------------------------------------------------------
tab_overview, tab_trends, tab_geo, tab_search, tab_data = st.tabs(
    ["📊 Overview", "📈 Trends & Growth", "🌍 Genres & Countries", "🔎 Search a Title", "🔍 Explore Data"]
)

# ================================ OVERVIEW ================================
with tab_overview:
    c1, c2 = st.columns(2)

    with c1:
        type_count = fdf["type"].value_counts().reset_index()
        type_count.columns = ["Type", "Count"]
        fig = px.pie(
            type_count, names="Type", values="Count", hole=0.45,
            title="Movies vs TV Shows", color="Type",
            color_discrete_map={"Movie": "#E50914", "TV Show": "#564D4D"},
        )
        fig.update_layout(legend=dict(orientation="h", y=-0.1))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        rating_count = fdf["rating"].value_counts().reset_index()
        rating_count.columns = ["Rating", "Count"]
        fig = px.bar(
            rating_count.sort_values("Count"), x="Count", y="Rating", orientation="h",
            title="Ratings Distribution", color="Count", color_continuous_scale="Reds",
        )
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        fig = px.histogram(
            fdf, x="release_year", color="type", nbins=40,
            title="Release Year Distribution", barmode="group", opacity=0.75,
            color_discrete_map={"Movie": "#E50914", "TV Show": "#564D4D"},
        )
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        movie_dur = fdf.loc[fdf["type"] == "Movie", "duration_minutes"].dropna()
        if not movie_dur.empty:
            fig = px.histogram(
                movie_dur, nbins=30, title="Movie Duration Distribution (minutes)",
                color_discrete_sequence=["#E50914"],
            )
            fig.update_layout(showlegend=False,bargap = 0.1, xaxis_title="Minutes", yaxis_title="Number of Movies")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No movies in the current filter selection.")

    st.subheader("Longest Movies")
    longest = (
        fdf[fdf["type"] == "Movie"]
        .dropna(subset=["duration_minutes"])
        .sort_values("duration_minutes", ascending=False)
        .head(10)[["title", "duration_minutes", "release_year", "listed_in"]]
        .rename(columns={"duration_minutes": "Minutes", "title": "Title",
                          "release_year": "Release Year", "listed_in": "Genre(s)"})
        .reset_index(drop=True)
    )
    st.dataframe(longest, use_container_width=True, hide_index=True)

    st.subheader("Content Rating vs Type")
    rating_type = fdf.groupby(["rating", "type"]).size().reset_index(name="Count")
    fig = px.bar(
        rating_type, x="rating", y="Count", color="type", barmode="group",
        title="Rating Composition by Content Type",
        color_discrete_map={"Movie": "#E50914", "TV Show": "#564D4D"},
    )
    fig.update_layout(xaxis_title="Rating", xaxis={"categoryorder": "total descending"})
    st.plotly_chart(fig, use_container_width=True)

# ============================= TRENDS & GROWTH =============================
with tab_trends:
    yearly = fdf.dropna(subset=["year_added"]).groupby("year_added").size().reset_index(name="Titles Added")
    yearly["year_added"] = yearly["year_added"].astype(int)
    fig = px.line(
        yearly, x="year_added", y="Titles Added", markers=True,
        title="Titles Added to Netflix per Year",
    )
    fig.update_traces(line_color="#E50914")
    st.plotly_chart(fig, use_container_width=True)
    if 2020 in yearly["year_added"].values or 2021 in yearly["year_added"].values:
        st.caption(
            "2019-2020 shows the sharpest jump in additions, with a pullback afterward - "
            "consistent with Netflix's aggressive content push right before/during the pandemic period."
        )

    c1, c2 = st.columns(2)
    with c1:
        by_type_year = (
            fdf.dropna(subset=["year_added"]).groupby(["year_added", "type"]).size().reset_index(name="Count")
        )
        by_type_year["year_added"] = by_type_year["year_added"].astype(int)
        fig = px.line(
            by_type_year, x="year_added", y="Count", color="type", markers=True,
            title="Movies vs TV Shows Added per Year",
            color_discrete_map={"Movie": "#E50914", "TV Show": "#564D4D"},
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        month_order = ["January","February","March","April","May","June",
                        "July","August","September","October","November","December"]
        by_month = fdf.dropna(subset=["month_added"]).groupby("month_added").size()
        by_month = by_month.reindex(month_order).reset_index()
        by_month.columns = ["Month", "Count"]
        fig = px.bar(by_month, x="Month", y="Count", title="Titles Added by Month (seasonality)",
                     color_discrete_sequence=["#E50914"])
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Genre Growth Race")
    st.caption("Cumulative title count for the top genres, animated year by year - press play.")
    genre_year = fdf.dropna(subset=["year_added"]).explode("genre_list")
    genre_year["year_added"] = genre_year["year_added"].astype(int)
    top8 = genre_year["genre_list"].value_counts().head(8).index.tolist()
    genre_year = genre_year[genre_year["genre_list"].isin(top8)]

    counts = genre_year.groupby(["year_added", "genre_list"]).size().unstack(fill_value=0)
    all_years = range(int(fdf["year_added"].min()), int(fdf["year_added"].max()) + 1)
    counts = counts.reindex(all_years, fill_value=0).sort_index()
    cumulative = counts.cumsum()
    race_df = cumulative.reset_index().melt(id_vars="year_added", var_name="Genre", value_name="Cumulative Titles")

    fig = px.bar(
        race_df, x="Cumulative Titles", y="Genre", color="Genre", orientation="h",
        animation_frame="year_added", range_x=[0, race_df["Cumulative Titles"].max() * 1.1],
        title="Cumulative Genre Growth Over Time",
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

# ============================ GENRES & COUNTRIES ============================
with tab_geo:
    c1, c2 = st.columns(2)
    with c1:
        genre_exp = fdf.explode("genre_list")
        top_genres = genre_exp["genre_list"].value_counts().head(10).reset_index()
        top_genres.columns = ["Genre", "Count"]
        fig = px.bar(
            top_genres.sort_values("Count"), x="Count", y="Genre", orientation="h",
            title="Top 10 Genres", color="Count", color_continuous_scale="Reds",
        )
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        country_exp = fdf.explode("country_list")
        top_ctry = (
            country_exp["country_list"].value_counts().drop("Not Defined", errors="ignore").head(10).reset_index()
        )
        top_ctry.columns = ["Country", "Count"]
        fig = px.bar(
            top_ctry.sort_values("Count"), x="Count", y="Country", orientation="h",
            title="Top 10 Content-Producing Countries", color="Count", color_continuous_scale="Reds",
        )
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("World Map - Titles Produced by Country")
    map_df = country_exp["country_list"].value_counts().drop("Not Defined", errors="ignore").reset_index()
    map_df.columns = ["Country", "Count"]
    fig = px.choropleth(
        map_df, locations="Country", locationmode="country names", color="Count",
        color_continuous_scale="Reds",
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Full Genre Frequency Table (all genres)"):
        full_genre_freq = genre_exp["genre_list"].value_counts().reset_index()
        full_genre_freq.columns = ["Genre", "Count"]
        st.dataframe(full_genre_freq, use_container_width=True, hide_index=True, height=400)

    st.subheader("Country x Genre Heatmap")
    st.caption("Top 15 countries vs top 15 genres, by number of titles.")
    top15_countries = (
        country_exp["country_list"].value_counts().drop("Not Defined", errors="ignore").head(15).index.tolist()
    )
    top15_genres = genre_exp["genre_list"].value_counts().head(15).index.tolist()

    heat_source = fdf.explode("country_list").explode("genre_list")
    heat_source = heat_source[
        heat_source["country_list"].isin(top15_countries) & heat_source["genre_list"].isin(top15_genres)
    ]
    pivot = (
        heat_source.groupby(["country_list", "genre_list"]).size().unstack(fill_value=0)
        .reindex(index=top15_countries, columns=top15_genres, fill_value=0)
    )
    fig = px.imshow(
        pivot, color_continuous_scale="Reds", aspect="auto",
        labels=dict(x="Genre", y="Country", color="Titles"),
    )
    fig.update_layout(height=550)
    st.plotly_chart(fig, use_container_width=True)

# ================================== SEARCH ==================================
with tab_search:
    st.subheader("Look up a title")
    query = st.selectbox(
        "Start typing a title...",
        options=[""] + sorted(df["title"].dropna().unique().tolist()),
        index=0,
    )

    if query:
        row = df[df["title"] == query].iloc[0]
        tmdb = fetch_tmdb_details(query, tmdb_api_key) if tmdb_api_key else None

        if tmdb and tmdb.get("backdrop_url"):
            st.image(tmdb["backdrop_url"], use_container_width=True)

        col_img, col_info = st.columns([1, 2])

        with col_img:
            poster_url = tmdb.get("poster_url") if tmdb else None
            if poster_url:
                st.image(poster_url, use_container_width=True)
            else:
                st.image("no.jpg")
                if not tmdb_api_key:
                    st.caption("Add a free TMDb API key in the sidebar to show posters here.")

        with col_info:
            st.markdown(f"### {row['title']}  ({row['release_year']})")
            st.markdown(f"**Type:** {row['type']}  |  **Rating:** {row['rating']}  |  **Duration:** {row['duration']}")
            st.markdown(f"**Genre(s):** {row['listed_in']}")
            st.markdown(f"**Country:** {row['country']}")
            st.markdown(f"**Director:** {row['director']}")
            st.markdown(f"**Cast:** {row['cast']}")
            if pd.notna(row["date_added"]):
                st.markdown(f"**Added to Netflix:** {row['date_added'].strftime('%B %d, %Y')}")
            if tmdb and tmdb.get("trailer_url"):
                st.markdown(f"**Trailer:** [Watch on YouTube]({tmdb['trailer_url']})")
            st.markdown("**Description:**")
            st.write(row["description"])
    else:
        st.caption("Pick a title above to see its full details.")

# ================================ EXPLORE DATA ================================
with tab_data:
    st.subheader(f"Filtered Titles ({len(fdf):,})")
    search_term = st.text_input("Quick filter by title keyword")
    view = fdf
    if search_term:
        view = view[view["title"].str.contains(search_term, case=False, na=False)]

    display_cols = ["title", "type", "country", "release_year", "rating",
                     "duration", "listed_in", "date_added"]
    st.dataframe(
        view[display_cols].sort_values("release_year", ascending=False).reset_index(drop=True),
        use_container_width=True,
        height=500,
    )
    csv = view[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button("Download filtered data as CSV", csv, "netflix_filtered.csv", "text/csv")

st.markdown("---")
st.caption("Built with Streamlit & Plotly - Data: Netflix Titles dataset - Posters (optional): TMDb API")
