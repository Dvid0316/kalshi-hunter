# Kalshi Hunter Picks

A small, read-only, paper-research page over Kalshi Hunter's existing SQLite database. It places no orders and requires no Kalshi login, keys, or credentials. The page reloads every 60 seconds.

## Run

From the Kalshi Hunter project root:

```sh
python picks_app/app.py
```

Then open `http://localhost:8080`. Install the pinned dependency first with `python -m pip install -r picks_app/requirements.txt` if Flask is not installed. By default the app reads `data/kalshi.db`; override with `KALSHI_HUNTER_DB=/path/to/kalshi.db`. `KALSHI_HUNTER_DIR` can point to the project root if the app folder is copied elsewhere.

The database connection uses SQLite `mode=ro` plus `PRAGMA query_only=ON`; no schema setup or project process is invoked.

## Tests

Run `python -m unittest discover -s picks_app/tests` from the project root.
