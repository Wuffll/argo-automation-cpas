import logging

from argo_ams_library import ArgoMessagingService
from argo_ams_library.amsexceptions import AmsException


LOG = logging.getLogger(__name__)


def init_ams(settings):
    """Initialise and return an ArgoMessagingService instance.

    Uses settings.ams.host, settings.ams.token and settings.ams.project
    from the loaded configuration.

    Args:
        settings: Settings object returned by config.get_settings().

    Returns:
        ArgoMessagingService instance ready for use.

    Raises:
        AmsException: if the initial connectivity check against the
                      subscription fails.
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

    if not ams.has_sub(settings.ams.subscription):
        raise AmsException(
            "Subscription %r does not exist in project %r"
            % (settings.ams.subscription, settings.ams.project)
        )

    LOG.info("Subscription %r confirmed", settings.ams.subscription)

    return ams
