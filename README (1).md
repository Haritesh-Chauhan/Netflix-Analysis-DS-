# Netflix Content Analysis Dashboard

An interactive Streamlit dashboard built on top of your Netflix titles EDA notebook.

## Setup

```bash
pip install -r requirements.txt
```

## Run

Make sure `netflix_titles.csv` is in the same folder as `app.py`, then:

```bash
streamlit run app.py
```

It will open at `http://localhost:8501`.

## What's inside

- **Sidebar filters**: content type, release year range, genre, country, rating, and a title search box — all charts and the data table update live.
- **Overview tab**: Movie vs TV Show split, ratings breakdown, movie duration histogram, TV show season counts.
- **Genres & Countries tab**: top 10 genres, top 10 producing countries, and a world choropleth map.
- **Trends Over Time tab**: titles added per year, movies vs TV shows added per year, monthly seasonality, release year distribution.
- **Explore Data tab**: a searchable/filterable table of the underlying titles with a CSV download button.

## Fix vs. your original notebook

Your notebook's `handle_rate()` function pulled the first number out of `duration` for every row, which mixed movie **minutes** with TV show **seasons** into a single meaningless number (and mean). This dashboard splits `duration` into `duration_minutes` (movies only) and `duration_seasons` (TV shows only), so the stats and charts for each are actually comparable.

## Notes

- `country` and `listed_in` can contain multiple comma-separated values per title. Genre filtering matches on *any* genre a title belongs to; country charts use the *first listed* country as the "primary" country to avoid double-counting.
- Rows with unparseable `date_added` are simply excluded from the time-based charts (10 rows in the current dataset).
