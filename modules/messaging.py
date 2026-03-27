import logging

from argo_ams_library import ArgoMessagingService
from argo_ams_library.amsexceptions import AmsException, AmsServiceException


LOG = logging.getLogger(__name__)


def init_ams(settings):
    """Initialise and return an ArgoMessagingService instance.

    Uses settings.ams.host, settings.ams.token and settings.ams.project
    from the loaded configuration. Exits with status 1 on any AMS error.

    Args:
        settings: Settings object returned by config.get_settings().

    Returns:
        ArgoMessagingService instance ready for use.
    """
    ams = ArgoMessagingService(
        endpoint=settings.ams.host,
        token=settings.ams.token,
        project=settings.ams.project,
    )

    LOG.info(
        "Initialised AMS client for project=%s host=%s subscription=%s",
        settings.ams.project,
        settings.ams.host,
        settings.ams.subscription,
    )

    try:
        sub_exists = ams.has_sub(settings.ams.subscription)
    except AmsServiceException as exc:
        LOG.error(
            "AMS request failed for project=%s host=%s: %s (HTTP %s)",
            settings.ams.project,
            settings.ams.host,
            exc.msg,
            exc.code,
        )
        raise SystemExit(1)

    if not sub_exists:
        LOG.error(
            "Subscription %r does not exist in project %r",
            settings.ams.subscription,
            settings.ams.project,
        )
        raise SystemExit(1)

    LOG.info("Subscription %r confirmed", settings.ams.subscription)

    return ams
