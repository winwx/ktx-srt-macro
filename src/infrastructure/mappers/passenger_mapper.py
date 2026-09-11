"""Passenger mapper for converting between domain and infrastructure models"""
from src.domain.models.entities import Passenger
from src.domain.models.enums import PassengerType
from src.infrastructure.external.ktx import AdultPassenger, ChildPassenger, SeniorPassenger, Passenger as KorailPessenger


class PassengerMapper:
    """Maps a single passenger between domain and infrastructure layers"""

    @staticmethod
    def to_korail(passenger: Passenger) -> KorailPessenger:
        """Convert a single domain passenger to Korail format"""
        match passenger.passenger_type.value:
            case PassengerType.ADULT.value:
                return AdultPassenger(count=passenger.count)
            case PassengerType.CHILD.value:
                return ChildPassenger(count=passenger.count)
            case PassengerType.SENIOR.value:
                return SeniorPassenger(count=passenger.count)
