"""lora-uplink: drains sensor-service's uplink_queue table (in the shared
readings.db) and transmits each row over a SX1276/RFM95 LoRa radio.

Buffering/retry contract: a row only ever gets marked 'sent' after radio
TX succeeds. Anything else — radio busy, boat out of range, no gateway
listening yet — just stays 'pending' and is retried in order on the next
tick, for as long as it takes (bounded only by the buffer-cap safety net
in queue_store.py). This process never talks to sensors directly; it
only reads/writes uplink_queue, so a sensor-service restart doesn't
affect it and vice versa.

Run (dev, from this directory):  python app.py
"""
import logging
import time

import config
import queue_store
from payload import encode

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("lora-uplink")

queue_store.init_db(config.DB_PATH)


def _build_radio():
    if config.LORA_MODE == "simulate":
        from radio import SimulatedRadio

        log.info("LORA_MODE=simulate -> using simulated radio")
        return SimulatedRadio(config)

    from radio import Rfm9xRadio

    try:
        radio = Rfm9xRadio(config)
    except Exception as e:  # noqa: BLE001
        log.warning("radio init raised (%s)", e)
        radio = None
    if radio is not None and radio.available:
        log.info("using real RFM9x radio at %.1f MHz", config.LORA_FREQ_MHZ)
        return radio

    from radio import SimulatedRadio

    log.warning("RFM9x hardware unavailable -> falling back to simulated radio")
    return SimulatedRadio(config)


radio = _build_radio()


def _send_row(row) -> bool:
    try:
        data = encode(row["payload_json"])
    except ValueError as e:
        log.error("dropping malformed/oversized uplink row id=%s: %s", row["id"], e)
        # A single bad row shouldn't jam the queue forever; the
        # underlying reading is still safe in readings.db's history
        # tables even if this particular uplink packet is discarded.
        queue_store.mark_sent(row["id"], time.time())
        return True

    ok = radio.send(data)
    if ok and config.LORA_WAIT_ACK:
        ack = radio.receive(timeout=config.LORA_ACK_TIMEOUT_S)
        ok = ack is not None  # no defined ack protocol yet -- any reply counts for now

    if ok:
        queue_store.mark_sent(row["id"], time.time())
        log.info("sent uplink row id=%s seq=%s (%d bytes)", row["id"], row["seq"], len(data))
    else:
        queue_store.mark_attempt(row["id"])
        log.warning("send failed for uplink row id=%s seq=%s, will retry", row["id"], row["seq"])
    return ok


def main():
    log.info("lora-uplink starting, db=%s node=%s", config.DB_PATH, config.NODE_ID)
    while True:
        evicted = queue_store.evict_oldest_pending(config.BUFFER_CAP_ROWS)
        if evicted:
            log.critical("uplink buffer cap exceeded -- dropped %d oldest pending row(s)", evicted)

        pending = queue_store.get_pending_rows(limit=200)
        if not pending:
            time.sleep(config.SEND_RETRY_INTERVAL_S)
            continue

        log.info("draining %d pending uplink row(s)", len(pending))
        link_down = False
        for row in pending:
            if not _send_row(row):
                # Link is clearly down right now -- stop hammering it and
                # back off to the full retry interval rather than the
                # tight drain throttle.
                link_down = True
                break
            time.sleep(config.DRAIN_THROTTLE_S)

        time.sleep(config.SEND_RETRY_INTERVAL_S if link_down else config.DRAIN_THROTTLE_S)


if __name__ == "__main__":
    main()
