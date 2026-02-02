def test_upload_fit_empty_result_confirmed(monkeypatch, tmp_path):
    """Empty upload result should be confirmed as duplicate by time search."""
    from fitness_toolkit.clients.garmin import GarminClient

    fit = tmp_path / "a.fit"
    fit.write_bytes(b"x")

    client = GarminClient()
    client.authenticated = True

    class _Resp:
        def json(self):
            return {"detailedImportResult": {"successes": [], "failures": []}}

    class _Client:
        def post(self, *args, **kwargs):
            return _Resp()

    client._client = _Client()

    # Confirm duplicate by returning a matching activity in get_activities
    monkeypatch.setattr(
        client,
        "get_activities",
        lambda start_date, end_date, activity_type=None: [
            {"activityId": "999", "startTimeLocal": "2024-01-15 08:30:00"}
        ],
    )

    activity_id = client.upload_fit(
        fit,
        activity_name=None,
        start_time="2024-01-15 08:30:30",
    )
    assert activity_id == "999"


def test_upload_fit_empty_result_unconfirmed(monkeypatch, tmp_path):
    """Empty upload result should fail when not confirmable as duplicate."""
    from fitness_toolkit.clients.garmin import GarminClient

    fit = tmp_path / "a.fit"
    fit.write_bytes(b"x")

    client = GarminClient()
    client.authenticated = True

    class _Resp:
        def json(self):
            return {"detailedImportResult": {"successes": [], "failures": []}}

    class _Client:
        def post(self, *args, **kwargs):
            return _Resp()

    client._client = _Client()

    monkeypatch.setattr(
        client,
        "get_activities",
        lambda start_date, end_date, activity_type=None: [],
    )

    activity_id = client.upload_fit(
        fit,
        activity_name=None,
        start_time="2024-01-15 08:30:30",
    )
    assert activity_id is None
