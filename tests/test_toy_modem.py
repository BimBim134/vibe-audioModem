"""The toy modem: a deliberately simple BPSK modem used to check the bench itself."""

from bench.toy import ToyModem


def test_a_message_survives_a_noiseless_round_trip():
    modem = ToyModem()
    samples = modem.modulate(b"Hi!", "standard")
    receptions = modem.demodulate(samples)
    assert [r.message for r in receptions] == [b"Hi!"]
