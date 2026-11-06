# Rewrite from scratch; keep the old code only as a tagged reference

The first prototype (GMSK at 200 baud on GNU Radio, six processes, ZeroMQ buses) is frozen under the git tag `legacy-v0` and read only for ideas. The new modem is written from zero in a new package. We did not fix the legacy bugs or use it as a test oracle, because its signals are not known to be valid and the product goal (decoding near the noise floor in a narrow band) needs a different physical layer, not a repaired one.
