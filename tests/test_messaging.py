import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from argo_ams_library.amsexceptions import AmsServiceException

from argo_automation_cpas.messaging import init_ams


@pytest.fixture
def settings():
    return SimpleNamespace(
        ams=SimpleNamespace(
            host="api.devel.msg.argo.grnet.gr",
            token="test-token",
            project="TEST-PROJECT",
            subscription="events-sub-1",
        )
    )


@patch("argo_automation_cpas.messaging.ArgoMessagingService")
def test_init_ams_returns_instance(mock_ams_cls, settings):
    mock_ams = MagicMock()
    mock_ams.has_sub.return_value = True
    mock_ams_cls.return_value = mock_ams

    result = init_ams(settings)

    mock_ams_cls.assert_called_once_with(
        endpoint=settings.ams.host,
        token=settings.ams.token,
        project=settings.ams.project,
    )
    mock_ams.has_sub.assert_called_once_with(settings.ams.subscription)
    assert result is mock_ams


@patch("argo_automation_cpas.messaging.ArgoMessagingService")
def test_init_ams_service_exception_exits(mock_ams_cls, settings):
    mock_ams = MagicMock()
    mock_ams.has_sub.side_effect = AmsServiceException(
        json={"error": "Unauthorized", "status_code": 401, "status": "UNAUTHORIZED"}
    )
    mock_ams_cls.return_value = mock_ams

    with pytest.raises(SystemExit) as exc_info:
        init_ams(settings)

    assert exc_info.value.code == 1


@patch("argo_automation_cpas.messaging.ArgoMessagingService")
def test_init_ams_missing_subscription_exits(mock_ams_cls, settings):
    mock_ams = MagicMock()
    mock_ams.has_sub.return_value = False
    mock_ams_cls.return_value = mock_ams

    with pytest.raises(SystemExit) as exc_info:
        init_ams(settings)

    assert exc_info.value.code == 1
