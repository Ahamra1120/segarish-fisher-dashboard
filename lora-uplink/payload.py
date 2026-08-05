"""Wire-format helpers for the compact uplink payload.

sensor-service already builds the compact, self-describing JSON string
(short keys, rounded precision — see sensor-service/app.py's
build_uplink_payload) and stores it verbatim in uplink_queue.payload_json.
This module's job is just turning that string into bytes safe to hand to
the radio (with a sanity size check, since LoRa packets are tiny) and
back, for testing/debugging.
"""
import json

# Keep comfortably under the ~255-byte hard cap most LoRa radios enforce
# per packet, leaving headroom for reasonable airtime at low spreading
# factors. A well-formed payload from sensor-service should never get
# close to this.
MAX_PAYLOAD_BYTES = 200


def encode(payload_json: str) -> bytes:
    data = payload_json.encode("utf-8")
    if len(data) > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"uplink payload too large for LoRa ({len(data)}B > {MAX_PAYLOAD_BYTES}B): {payload_json!r}"
        )
    return data


def decode(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))
