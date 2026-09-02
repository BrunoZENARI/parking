import json
import logging
import os

import aio_pika

from application.use_cases.confirm_entry import ConfirmEntryUseCase
from application.use_cases.confirm_exit import ConfirmExitUseCase
from application.use_cases.update_repartition import UpdateRepartitionUseCase
from domain.entities.category import CategoryName, CommercialType

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")


class ParkingConsumer:

    def __init__(
        self,
        confirm_entry_use_case: ConfirmEntryUseCase,
        confirm_exit_use_case: ConfirmExitUseCase,
        update_repartition_use_case: UpdateRepartitionUseCase,
    ):
        self._confirm_entry = confirm_entry_use_case
        self._confirm_exit = confirm_exit_use_case
        self._update_repartition = update_repartition_use_case

    async def start(self):
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()

        await channel.set_qos(prefetch_count=1)

        queue = await channel.declare_queue("parking.events", durable=True)

        await queue.consume(self._dispatch)
        logger.info("Consumer RabbitMQ démarré — écoute sur parking.events")
        return connection

    async def _dispatch(self, message: aio_pika.IncomingMessage):
        async with message.process():
            try:
                body = json.loads(message.body.decode())
                event_type = body.get("event_type")
                logger.info(f"Événement reçu : {event_type}")

                if event_type == "vehicle.entry.confirmed":
                    await self._handle_entry_confirmed(body)
                elif event_type == "vehicle.exit.confirmed":
                    await self._handle_exit_confirmed(body)
                elif event_type == "parking.repartition.update":
                    await self._handle_repartition_update(body)
                elif event_type == "booking.spot.reserved":
                    await self._handle_booking_reserved(body)
                else:
                    logger.warning(f"Événement inconnu : {event_type}")

            except Exception as e:
                logger.error(f"Erreur traitement message : {e}")

    async def _handle_entry_confirmed(self, body: dict):
        hold_id = body["hold_id"]
        await self._confirm_entry.execute(hold_id=hold_id)
        logger.info(f"Entrée confirmée pour hold {hold_id}")

    async def _handle_exit_confirmed(self, body: dict):
        category_name = CategoryName(body["category_name"])
        commercial_type = CommercialType(body["commercial_type"])
        await self._confirm_exit.execute(
            category_name=category_name,
            commercial_type=commercial_type,
        )
        logger.info(f"Sortie confirmée pour {category_name} / {commercial_type}")

    async def _handle_repartition_update(self, body: dict):
        category_name = CategoryName(body["category_name"])
        new_walkin = body["new_walkin_capacity"]
        new_booking = body["new_booking_capacity"]
        await self._update_repartition.execute(
            category_name=category_name,
            new_walkin_capacity=new_walkin,
            new_booking_capacity=new_booking,
        )
        logger.info(f"Répartition mise à jour pour {category_name}")

    async def _handle_booking_reserved(self, body: dict):
        category_name = CategoryName(body["category_name"])
        await self._confirm_exit.execute(
            category_name=category_name,
            commercial_type=CommercialType.BOOKING,
        )
        logger.info(f"Place booking réservée pour {category_name}")
