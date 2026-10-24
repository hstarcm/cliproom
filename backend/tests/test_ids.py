"""FR-1/SR-1: room ID generation — length, alphabet, uniqueness."""

from app.ids import BASE62_ALPHABET, is_base62, new_room_id


def test_room_id_length_and_alphabet():
    for _ in range(100):
        rid = new_room_id()
        assert len(rid) >= 22
        assert is_base62(rid)
        assert rid.isascii()


def test_room_id_uniqueness_10k():
    seen = {new_room_id() for _ in range(10_000)}
    assert len(seen) == 10_000


def test_alphabet_is_base62():
    assert len(BASE62_ALPHABET) == 62
    assert set("0123456789") | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ") | set("abcdefghijklmnopqrstuvwxyz") == set(BASE62_ALPHABET)
