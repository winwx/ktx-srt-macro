"""Unit tests for domain enums"""
import pytest
from src.domain.models.enums import PassengerType, TrainType


@pytest.mark.unit
@pytest.mark.domain
class TestPassengerType:
    """Tests for PassengerType enum"""

    def test_passenger_type_values(self):
        """Test that PassengerType has correct values"""
        assert PassengerType.ADULT.value == "adult"
        assert PassengerType.CHILD.value == "child"
        assert PassengerType.SENIOR.value == "senior"

    def test_passenger_type_members(self):
        """Test that PassengerType has all expected members"""
        passenger_types = list(PassengerType)
        assert len(passenger_types) == 3
        assert PassengerType.ADULT in passenger_types
        assert PassengerType.CHILD in passenger_types
        assert PassengerType.SENIOR in passenger_types

    def test_passenger_type_by_value(self):
        """Test accessing PassengerType by value"""
        assert PassengerType("adult") == PassengerType.ADULT
        assert PassengerType("child") == PassengerType.CHILD
        assert PassengerType("senior") == PassengerType.SENIOR

    def test_passenger_type_invalid_value(self):
        """Test that invalid value raises ValueError"""
        with pytest.raises(ValueError):
            PassengerType("invalid")

    def test_passenger_type_equality(self):
        """Test PassengerType equality"""
        assert PassengerType.ADULT == PassengerType.ADULT
        assert PassengerType.CHILD == PassengerType.CHILD
        assert PassengerType.ADULT != PassengerType.CHILD

    def test_passenger_type_string_representation(self):
        """Test PassengerType string representation"""
        assert str(PassengerType.ADULT) == "PassengerType.ADULT"
        assert PassengerType.ADULT.name == "ADULT"


@pytest.mark.unit
@pytest.mark.domain
class TestTrainType:
    """Tests for TrainType enum"""

    def test_train_type_values(self):
        """Test that TrainType has correct values"""
        assert TrainType.KTX.value == "ktx"
        assert TrainType.SAEMAEUL.value == "saemaeul"
        assert TrainType.MUGUNGHWA.value == "mugunghwa"
        assert TrainType.TONGGEUN.value == "tonggeun"
        assert TrainType.NURIRO.value == "nuriro"
        assert TrainType.ITX_CHEONGCHUN.value == "itx_cheongchun"
        assert TrainType.AIRPORT.value == "airport"

    def test_train_type_members(self):
        """Test that TrainType has all expected members"""
        train_types = list(TrainType)
        assert len(train_types) == 7
        assert TrainType.KTX in train_types
        assert TrainType.SAEMAEUL in train_types
        assert TrainType.MUGUNGHWA in train_types
        assert TrainType.TONGGEUN in train_types
        assert TrainType.NURIRO in train_types
        assert TrainType.ITX_CHEONGCHUN in train_types
        assert TrainType.AIRPORT in train_types

    def test_train_type_by_value(self):
        """Test accessing TrainType by value"""
        assert TrainType("ktx") == TrainType.KTX
        assert TrainType("mugunghwa") == TrainType.MUGUNGHWA

    def test_train_type_invalid_value(self):
        """Test that invalid value raises ValueError"""
        with pytest.raises(ValueError):
            TrainType("srt")

    def test_train_type_equality(self):
        """Test TrainType equality"""
        assert TrainType.KTX == TrainType.KTX
        assert TrainType.MUGUNGHWA == TrainType.MUGUNGHWA
        assert TrainType.KTX != TrainType.MUGUNGHWA

    def test_train_type_string_representation(self):
        """Test TrainType string representation"""
        assert str(TrainType.KTX) == "TrainType.KTX"
        assert TrainType.KTX.name == "KTX"

    def test_train_type_contains_ktx(self):
        """Test that TrainType contains KTX"""
        assert TrainType.KTX in TrainType

    def test_train_type_contains_mugunghwa(self):
        """Test that TrainType contains MUGUNGHWA"""
        assert TrainType.MUGUNGHWA in TrainType
