# Versioned solar inference artifacts

The three `solar_*.txt` files are LightGBM boosters used by the live forecast endpoint. They are
versioned because a deployed API must not retrain a model at request time. Their feature order,
calibration scale and training provenance are frozen in `solar_manifest.json`.

Demand models remain generated artifacts because the live warning currently uses an explicitly
labelled CEEW historical demand proxy. Run `python -m ml.forecast` to regenerate all six models.
