from saalr_core.ids import new_id


def test_new_id_is_uuid_v7():
    uid = new_id()
    assert uid.version == 7


def test_new_ids_are_time_ordered():
    a = new_id()
    b = new_id()
    assert b > a  # UUIDv7 is time-ordered