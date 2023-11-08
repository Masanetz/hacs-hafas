"""Sensor for HaFAS."""

from __future__ import annotations

from datetime import timedelta
import functools
from typing import Any

from pyhafas import HafasClient
from pyhafas.types.fptf import Journey, Station

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_OFFSET
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from .const import CONF_DESTINATION, CONF_ONLY_DIRECT, CONF_START, DOMAIN

ICON = "mdi:train"
SCAN_INTERVAL = timedelta(minutes=2)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up HaFAS sensor entities based on a config entry."""
    client: HafasClient = hass.data[DOMAIN][entry.entry_id]

    # Already verified to have at least one entry in config_flow.py
    start_station = (
        await hass.async_add_executor_job(client.locations, entry.data[CONF_START])
    )[0]
    destination_station = (
        await hass.async_add_executor_job(
            client.locations, entry.data[CONF_DESTINATION]
        )
    )[0]

    offset = timedelta(**entry.data[CONF_OFFSET])

    async_add_entities(
        [
            HaFAS(
                hass,
                client,
                start_station,
                destination_station,
                offset,
                entry.data[CONF_ONLY_DIRECT],
                entry.title,
                entry.entry_id,
            )
        ],
        True,
    )


class HaFAS(SensorEntity):
    """Implementation of a HaFAS sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: HafasClient,
        start_station: Station,
        destination_station: Station,
        offset: timedelta,
        only_direct: bool,
        title: str,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self.client = client
        self.origin = start_station
        self.destination = destination_station
        self.offset = offset
        self.only_direct = only_direct
        self._name = title

        self._attr_unique_id = entry_id

        self.journeys: list[Journey] = []

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self) -> str:
        """Return the icon for the frontend."""
        return ICON

    @property
    def native_value(self) -> str:
        """Return the departure time of the next train."""
        if (
            len(self.journeys) == 0
            or self.journeys[0].legs is None
            or len(self.journeys[0].legs) == 0
        ):
            return "No connection possible"

        first_leg = self.journeys[0].legs[0]

        value = first_leg.departure.strftime("%H:%M")
        if (
            first_leg.departureDelay is not None
            and first_leg.departureDelay != timedelta()
        ):
            delay = int(first_leg.departureDelay.total_seconds() // 60)

            value += f" + {delay}"

        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if (
            len(self.journeys) == 0
            or self.journeys[0].legs is None
            or len(self.journeys[0].legs) == 0
        ):
            return {}

        journey = self.journeys[0]
        first_leg = journey.legs[0]
        last_leg = journey.legs[-1]
        products = ", ".join([x.name for x in journey.legs if x.name is not None])[:-2]
        duration = timedelta() if journey.duration is None else journey.duration
        delay = (
            timedelta()
            if first_leg.departureDelay is None
            else first_leg.departureDelay
        )
        delay_arrival = (
            timedelta() if last_leg.arrivalDelay is None else last_leg.arrivalDelay
        )
        if (
            last_leg.arrivalDelay is not None
            and last_leg.arrivalDelay != timedelta()
        ):
            delay_arrival_minutes = int( last_leg.arrivalDelay.total_seconds() // 60)
            real_arrival = last_leg.arrival + last_leg.arrivalDelay
        else:
            real_arrival = last_leg.arrival
            delay_arrival_minutes = 0
        if (
            first_leg.departureDelay is not None
            and first_leg.departureDelay != timedelta()
        ):
            delay_minutes = int( first_leg.departureDelay.total_seconds() // 60)
            real_departure = first_leg.departure + first_leg.departureDelay
        else:
            real_departure = first_leg.departure
            delay_minutes = 0
            
        connections = {
            "departure": first_leg.departure.strftime("%H:%M"),
            "arrival": last_leg.arrival.strftime("%H:%M"),
            "transfers": len(journey.legs) - 1,
            "time": str(duration),
            "products": products,
            "ontime": delay == timedelta(),
            "delay": str(delay),
            "delay_minutes": delay_minutes,
            "cancelled": first_leg.cancelled,
            "delay_arrival": str(delay_arrival),
            "delay_arrival_minutes": delay_arrival_minutes,
            "real_departure": real_departure.strftime("%H:%M"),
            "real_arrival": real_arrival.strftime("%H:%M"),
        }
        
        next_departure = "No connection possible"
        next_cancelled = 'false'
        next_delay = "0:00:00"
        next_delay_minutes = 0
        next_real_departure = "No connection possible"
        next_arrival = "No connection possible"
        next_real_arrival = "No connection possible"
        next_delay_arrival = "0:00:00"
        next_delay_arrival_minutes = 0
        if (
            len(self.journeys) > 1
            and self.journeys[1].legs is not None
            and len(self.journeys[1].legs) > 0
        ):
            next_leg = self.journeys[1].legs[0]
            next_departure = next_leg.departure
            next_cancelled = next_leg.cancelled
            next_arrival = self.journeys[1].legs[-1].arrival
            next_real_arrival = next_arrival
            if (
                next_leg.departureDelay is not None
                and next_leg.departureDelay != timedelta()
            ):
                next_delay_minutes = int( next_leg.departureDelay.total_seconds() // 60)
                next_real_departure = next_leg.departure + next_leg.departureDelay
            else:
                next_real_departure = next_leg.departure
            if (
                self.journeys[1].legs[-1].arrivalDelay is not None
                and self.journeys[1].legs[-1].arrivalDelay != timedelta()
            ):
                next_delay_arrival_minutes = int( self.journeys[1].legs[-1].arrivalDelay.total_seconds() // 60)
                next_real_arrival = next_arrival + self.journeys[1].legs[-1].arrivalDelay
            next_delay = (
                timedelta()
                if next_leg.departureDelay is None
                else next_leg.departureDelay
            )
            
        connections["next_departure"] = next_departure.strftime("%H:%M")
        connections["next_cancelled"] = next_cancelled
        connections["next_delay"] = str(next_delay)
        connections["next_delay_minutes"] = next_delay_minutes
        connections["next_real_departure"] = next_real_departure.strftime("%H:%M")
        connections["next_arrival"] = next_arrival.strftime("%H:%M")
        connections["next_real_arrival"] = next_real_arrival.strftime("%H:%M")
        connections["next_delay_arrival"] = str(next_delay_arrival)
        connections["next_delay_arrival_minutes"] = next_delay_arrival_minutes

        next_on_departure = "No connection possible"
        next_on_cancelled = 'false'
        next_on_delay = "0:00:00"
        next_on_delay_minutes = 0
        next_on_real_departure = "No connection possible"
        next_on_arrival = "No connection possible"
        if (
            len(self.journeys) > 2
            and self.journeys[2].legs is not None
            and len(self.journeys[2].legs) > 0
        ):
            next_on_leg = self.journeys[2].legs[0]
            next_on_departure = next_on_leg.departure
            next_on_cancelled = next_on_leg.cancelled
            next_on_arrival = self.journeys[1].legs[-1].arrival
            if (
                next_on_leg.departureDelay is not None
                and next_on_leg.departureDelay != timedelta()
            ):
                next_on_delay_minutes = int( next_on_leg.departureDelay.total_seconds() // 60)
                next_on_real_departure = next_on_leg.departure + next_on_leg.departureDelay
            else:
                next_on_real_departure = next_on_leg.departure
            next_on_delay = (
                timedelta()
                if next_on_leg.departureDelay is None
                else next_on_leg.departureDelay
            )

        connections["next_on_departure"] = next_on_departure.strftime("%H:%M")
        connections["next_on_cancelled"] = next_on_cancelled
        connections["next_on_delay"] = str(next_on_delay)
        connections["next_on_delay_minutes"] = next_on_delay_minutes
        connections["next_on_real_departure"] = next_on_real_departure.strftime("%H:%M")
        connections["next_on_arrival"] = next_arrival.strftime("%H:%M")

        return connections

    async def async_update(self) -> None:
        """Update the journeys using pyhafas."""

        self.journeys = await self.hass.async_add_executor_job(
            functools.partial(
                self.client.journeys,
                origin=self.origin,
                destination=self.destination,
                date=dt_util.as_local(dt_util.utcnow() + self.offset),
                max_changes=0 if self.only_direct else -1,
                max_journeys=3,
            )
        )
