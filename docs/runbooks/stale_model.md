# Stale or broken solar model

**Symptom.** `data/monitor/WARN` exists, or live inference fails with `checksum mismatch for solar_v2_p50.txt` or
`live feature schema does not match the trained model`.

**Check.**
1. `cat data/monitor/WARN`: it names coverage (outside 70 to 90% over 14 days) or MAE (more than 25% above the
   model card baseline).
2. `cat data/monitor/conformal_state.json`: the interval width in use and the date it was computed.
3. Checksum errors: `git status ml/models`. The manifest's SHA-256 values are of the committed LF bytes
   (`.gitattributes` stores `ml/models/*.txt` with LF); a file re-saved with CRLF fails the check.

**Fix.**
- Coverage drift: the monitor already re-estimates the width from the last 30 days each night. If the warning
  persists for a week, retrain: `python -m scripts.download_solar_v2 && python -m ml.solar_v2`, and commit the new
  models only if the output says `"gate_g3_passes": true`.
- MAE drift: check `ml/reports/solar_v2.json` for an NWP model that dropped out of gate G2; retrain as above.
- Checksum mismatch: `git checkout -- ml/models`. Never edit a model file by hand.

**Who decides.** The model owner (Person B) decides on retraining; a retrained model ships only if gate G3 passes.
