from typing import List
from datetime import datetime
from src.domain.services.train_service import TrainService
from src.domain.models.entities import (
    Station, TrainSchedule, ReservationRequest, ReservationResult, CreditCard, PaymentResult
)
from src.domain.models.enums import TrainType
from src.infrastructure.external.ktx import Korail, CardPaymentConfig, TrainType as KorailTrainType
from src.infrastructure.mappers import PassengerMapper
from src.constants.stations import KTX_STATIONS


# domain TrainType -> Korail 그룹코드 매핑 (인프라 세부사항이므로 어댑터에 둔다)
_DOMAIN_TO_KORAIL_TRAIN_TYPE = {
    TrainType.KTX: KorailTrainType.KTX,
    TrainType.SAEMAEUL: KorailTrainType.SAEMAEUL,
    TrainType.MUGUNGHWA: KorailTrainType.MUGUNGHWA,
    TrainType.TONGGEUN: KorailTrainType.TONGGUEN,
    TrainType.NURIRO: KorailTrainType.NURIRO,
    TrainType.ITX_CHEONGCHUN: KorailTrainType.ITX_CHEONGCHUN,
    TrainType.AIRPORT: KorailTrainType.AIRPORT,
}


class KTXService(TrainService):
    """KTX/Korail train service implementation"""

    def __init__(self):
        self._korail = Korail(None, None, auto_login=False)
        self._logged_in = False

    def login(self, user_id: str, password: str) -> bool:
        """Login to Korail service"""
        try:
            result = self._korail.login(user_id, password)
            self._logged_in = result
            return result
        except Exception as e:
            self._logged_in = False
            return False

    def logout(self) -> bool:
        """Logout from Korail service"""
        try:
            self._korail.logout()
            self._logged_in = False
            return True
        except Exception:
            return False

    def search_trains(self, request: ReservationRequest) -> List[TrainSchedule]:
        """Search for available KTX trains"""
        if not self._logged_in:
            return []

        try:
            # Convert domain request to Korail format
            trains = self._korail.search_train(
                dep=request.departure_station,
                arr=request.arrival_station,
                date=request.departure_date.strftime("%Y%m%d"),
                time=request.departure_time,
                train_type=self._to_korail_train_type(request.train_type),
                include_no_seats=True,
            )

            schedules = []
            for train in trains:
                schedule = TrainSchedule(
                    train_number=getattr(train, 'train_no', ''),
                    departure_station=request.departure_station,
                    arrival_station=request.arrival_station,
                    departure_time=self._parse_time(train.dep_date + train.dep_time),
                    arrival_time=self._parse_time(train.arr_date + train.arr_time),
                    train_type=self._convert_train_type(getattr(train, 'train_type_name', '')),
                    available_seats=self._get_available_seats(train),
                    price=getattr(train, 'adultcharge', None)
                )
                schedules.append(schedule)

            return schedules
        except Exception:
            return []

    def reserve_train(self, schedule: TrainSchedule, request: ReservationRequest) -> ReservationResult:
        """Reserve a KTX train"""
        if not self._logged_in:
            return ReservationResult(success=False, message="Not logged in")

        try:
            # Convert passengers to Korail format
            passengers = [PassengerMapper.to_korail(p) for p in request.passengers]

            # Find the train again for reservation
            trains = self._korail.search_train(
                dep=request.departure_station,
                arr=request.arrival_station,
                date=request.departure_date.strftime("%Y%m%d"),
                time=request.departure_time,
                passengers=passengers,
                train_type=self._to_korail_train_type(request.train_type),
                include_no_seats=True,
            )

            target_train = None
            for train in trains:
                if train.train_no == schedule.train_number:
                    target_train = train
                    break

            if not target_train:
                return ReservationResult(success=False, message="Train not found")

            if not target_train.has_seat():
                return ReservationResult(success=False, message="No available seats")

            # Make reservation
            reservation = self._korail.reserve(train=target_train, passengers=passengers)

            if reservation:
                return ReservationResult(
                    success=True,
                    reservation_number=reservation.rsv_id,
                    message="Reservation successful",
                    train_schedule=schedule
                )
            else:
                return ReservationResult(success=False, message="Reservation failed")

        except Exception as e:
            return ReservationResult(success=False, message=f"Reservation error: {e}")

    def get_stations(self) -> List[Station]:
        """Get list of KTX stations"""
        return [Station(station.name, station.code) for station in KTX_STATIONS]

    def is_logged_in(self) -> bool:
        """Check if logged in to KTX service"""
        return self._logged_in

    def get_account_info(self) -> dict:
        """로그인된 계정 정보를 반환한다 (로그인 응답 파싱 결과를 그대로 전달).

        로그인 전이거나 값이 없으면 각 항목은 None이다.
        """
        return {
            "id": getattr(self._korail, "korail_id", None),
            "membership_number": getattr(self._korail, "membership_number", None),
            "name": getattr(self._korail, "name", None),
            "email": getattr(self._korail, "email", None),
        }

    @property
    def service_name(self) -> str:
        """Name of the service"""
        return "Korail"

    def _parse_time(self, time_str: str) -> datetime:
        """Parse time string to datetime"""
        return datetime.strptime(time_str, "%Y%m%d%H%M%S")

    def _to_korail_train_type(self, train_type: TrainType) -> str:
        """Convert domain TrainType(or None="전체") to Korail 그룹코드"""
        if train_type is None:
            return KorailTrainType.ALL
        return _DOMAIN_TO_KORAIL_TRAIN_TYPE.get(train_type, KorailTrainType.ALL)

    def _convert_train_type(self, train_type_name: str) -> TrainType:
        """Convert Korail train type name(한글, h_trn_clsf_nm) to domain train type"""
        if "KTX" in train_type_name.upper():
            return TrainType.KTX
        elif "무궁화" in train_type_name:
            return TrainType.MUGUNGHWA
        elif "새마을" in train_type_name:
            return TrainType.SAEMAEUL
        elif "누리로" in train_type_name:
            return TrainType.NURIRO
        elif "통근" in train_type_name:
            return TrainType.TONGGEUN
        elif "청춘" in train_type_name:
            return TrainType.ITX_CHEONGCHUN
        elif "공항" in train_type_name:
            return TrainType.AIRPORT
        else:
            # 매칭되지 않는 종류는 안전하게 KTX로 fallback (예외를 던지지 않음)
            return TrainType.KTX

    def _get_available_seats(self, train) -> int:
        """Get available seats count"""
        try:
            # Try to get seat availability information
            return getattr(train, 'seat_count', 0)
        except:
            return 0

    def payment_reservation(self, reservation: ReservationResult, credit_card: CreditCard) -> PaymentResult:
        """Pay for a reservation with credit card"""
        if not self._logged_in:
            return PaymentResult(success=False, message="Not logged in")

        target_reservation = next(
            (r for r in self._korail.reservations() if r.rsv_id == reservation.reservation_number),
            None,
        )

        if not target_reservation:
            return PaymentResult(success=False, message="Reservation not found")

        config = CardPaymentConfig(
            card_number=credit_card.number,
            expiry=credit_card.expire,
            password2=credit_card.password,
            birthdate6=credit_card.validation_number,
            expected_amount=target_reservation.price,
        )

        try:
            self._korail.pay_with_card(target_reservation, config)
            return PaymentResult(success=True, message="Payment successful", reservation_number=target_reservation.rsv_id)
        except Exception as e:
            return PaymentResult(success=False, message=f"Payment failed: {e}")