"""Worker do Outbox Relay (Deployment ``outbox-relay``): publica a outbox no Event Hubs.

    python -m pedidos.relay
"""

from __future__ import annotations

import logging
import signal

from edp_events import OutboxRelay

from pedidos.config import get_settings
from pedidos.db import create_db_engine, session_factory
from pedidos.persistence import outbox_table


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    if not settings.eventhub_namespace_fqdn:
        raise RuntimeError("EVENTHUB_NAMESPACE_FQDN é obrigatório para o relay")

    from edp_events.publishers.eventhubs import EventHubsPublisher
    from edp_events.registry import register_schemas

    log = logging.getLogger("pedidos.relay")
    if settings.register_schemas:
        # Registry efêmero (ADR-0010): o produtor registra a Published Language ao subir.
        try:
            register_schemas(settings.contracts_dir, settings.eventhub_namespace_fqdn, settings.schema_group)
        except Exception:  # noqa: BLE001 - registry indisponível não deve impedir a publicação
            log.exception("Falha ao registrar schemas no Schema Registry")

    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    relay = OutboxRelay(
        session_factory(create_db_engine(settings)),
        outbox_table,
        EventHubsPublisher(settings.eventhub_namespace_fqdn),
        batch_size=settings.relay_batch_size,
        poll_interval_seconds=settings.relay_poll_interval_seconds,
    )
    relay.run_forever(should_stop=lambda: stop)


if __name__ == "__main__":
    main()
