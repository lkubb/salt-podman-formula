"""
Execution module to interface with Podman through its REST API.

This is **very** basic at the moment and mostly wraps the
``podman`` Python module API.

All commands can target the system ``podman`` running as root
or a rootless ``podman`` running under a user account.

Note that the rootless API service usually requires lingering to be
enabled for the user account.

:depends: ``podman`` Python module
"""

import logging
from pathlib import Path

from salt.exceptions import CommandExecutionError

try:
    from podman.errors import APIError, ImageNotFound, NotFound, PodmanError

    from podman import PodmanClient, api

    HAS_PODMAN = True
except ImportError:
    HAS_PODMAN = False


log = logging.getLogger(__name__)

__virtualname__ = "podman"


def __virtual__():
    if HAS_PODMAN:
        return __virtualname__
    return False, "The `podman` Python library could not be imported"


def _find_podman_sock(user=None):
    if user is None:
        sock = Path("/run/podman/podman.sock")
        if sock.exists():
            return "unix://" + str(sock)
        raise CommandExecutionError("Could not find podman socket")
    try:
        uid = __salt__["user.info"](user)["uid"]
    except KeyError as err:
        raise CommandExecutionError(f"Could not find uid of user {user}") from err
    sock = Path(f"/run/user/{uid}/podman/podman.sock")
    if sock.exists():
        return "unix://" + str(sock)
    raise CommandExecutionError(f"Could not find podman socket for user {user}")


def _filter_kwargs(kwargs):
    return {k: v for k, v in kwargs.items() if not k.startswith("_")}


def create(image, command=None, name=None, user=None, **kwargs):
    """
    Create a container.

    image
        The image to base the container on.

    command
        Command to run in the container.

    name
        The name for the container.

    user
        Create a rootless container under this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.

    kwargs
        Keyword arguments that are passed to the ``create`` method of the
        ContainersManager instance.

        https://github.com/containers/podman-py/blob/main/podman/domain/containers_create.py
    """
    is_retry = kwargs.pop("_is_retry", False)
    if "environment" in kwargs:
        if isinstance(kwargs["environment"], dict):
            kwargs["environment"] = {
                k: str(v) for k, v in kwargs["environment"].items()
            }
        elif isinstance(kwargs["environment"], list):
            map(str, kwargs["environment"])
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            try:
                res = client.containers.create(
                    image, command=command, name=name, **_filter_kwargs(kwargs)
                )
            except (APIError, ImageNotFound) as err:
                if isinstance(err, APIError) and "image not known" not in str(err):
                    raise
                if is_retry:
                    raise
                pull(image, user=user)
                return create(
                    image,
                    command=command,
                    name=name,
                    user=user,
                    _is_retry=True,
                    **kwargs,
                )
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res.attrs


def create_patched(image, command=None, name=None, user=None, **kwargs):
    """
    Create a container. This handles more arguments which are unsupported
    as of podman library version 4.4.1. It meddles with internals though.

    image
        The image to base the container on.

    command
        Command to run in the container.

    name
        The name for the container.

    user
        Create a rootless container under this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.

    kwargs
        Keyword arguments that are passed to the ``create`` method of the
        ContainersManager instance.

        Note that this also supports ``secret_env`` to set environment variables
        from secrets, which is not supported by the podman library as of v4.4.1.

        https://github.com/containers/podman-py/blob/main/podman/domain/containers_create.py
    """
    is_retry = kwargs.pop("_is_retry", False)
    params = {}
    for param in ("secret_env",):
        if param in kwargs:
            params[param] = kwargs.pop(param)
    if "environment" in kwargs:
        if isinstance(kwargs["environment"], dict):
            kwargs["environment"] = {
                k: str(v) for k, v in kwargs["environment"].items()
            }
        elif isinstance(kwargs["environment"], list):
            map(str, kwargs["environment"])

    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            payload = {"image": image, "command": command, "name": name}
            payload.update(kwargs)
            payload = client.containers._render_payload(payload)
            payload.update(params)
            payload = api.prepare_body(payload)
            try:
                response = client.containers.client.post(
                    "/containers/create",
                    headers={"content-type": "application/json"},
                    data=payload,
                )
                response.raise_for_status(not_found=ImageNotFound)
            except (APIError, ImageNotFound) as err:
                if isinstance(err, APIError) and "image not known" not in str(err):
                    raise
                if is_retry:
                    raise
                pull(image, user=user)
                return create_patched(
                    image,
                    command=command,
                    name=name,
                    user=user,
                    _is_retry=True,
                    **kwargs,
                )

            container_id = response.json()["Id"]
            res = client.containers.get(container_id)

    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res.attrs


def create_network(
    name,
    dns_enabled=None,
    driver=None,
    enable_ipv6=None,
    internal=None,
    ipam=None,
    labels=None,
    options=None,
    user=None,
):
    """
    Create a network.

    name
        The name of the network to create.

    dns_enabled
        When True, do not provision DNS for this network. (This is the description
        on the ``podman`` library, not sure if that's correct.)

        https://github.com/containers/podman-py/blob/main/podman/domain/networks_manager.py

    driver
        Which network driver to use when creating network.

    enable_ipv6
        Whether to enable IPv6 on the network.

    internal
        Restrict external access to the network.

    ipam
        Optional custom IP scheme for the network.

    labels
        Map of labels to set on the network.

    options
        Driver options.

    user
        Create a rootless container under this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.networks.create(
                name,
                dns_enabled=dns_enabled,
                driver=driver,
                enable_ipv6=enable_ipv6,
                internal=internal,
                ipam=ipam,
                labels=labels,
                options=options,
            )
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res.attrs


def create_pod(name, user=None, **kwargs):
    """
    Create a pod.

    name
        The name of the pod to create.

    user
        Create a rootless pod under this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.

    kwargs
        Supplemental keyword arguments for pod creation.

        https://docs.podman.io/en/latest/_static/api.html#tag/pods/operation/PodCreateLibpod
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.pods.create(name, **_filter_kwargs(kwargs))
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res.attrs


def create_secret(name, data, driver=None, user=None):
    """
    Create a secret.

    name
        The name of the secret to create.

    data
        Secret data to be registered with Podman.

    driver
        Secret driver to use.

    user
        Create a secret under this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.
    """
    if not isinstance(data, bytes):
        if not isinstance(data, str):
            raise CommandExecutionError("Need bytes or string as data")
        try:
            data = data.encode()
        except UnicodeEncodeError as err:
            raise CommandExecutionError(
                f"Could not encode data to bytes: {err}"
            ) from err
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.secrets.create(name, data, driver=driver)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res.attrs


def create_volume(name, driver=None, driver_opts=None, labels=None, user=None):
    """
    Create a volume.

    name
        The name of the volume to create.

    user
        Create a rootless volume under this user account. Requires the volumeman
        socket to run for this user, which usually requires lingering enabled.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.volumes.create(
                name, driver=driver, driver_opts=driver_opts, labels=labels
            )
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res.attrs


def df(user=None):
    """
    Check disk usage by Podman resources.

    user
        Check Podman running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.system.df()
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def exists(container, user=None):
    """
    Check whether a container exists.

    container
        The container name or ID to check for.

    user
        Check Podman running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.containers.exists(container)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def generate_systemd(
    ref,
    add_env=None,
    after=None,
    container_prefix="container",
    new=False,
    header=False,
    pod_prefix="pod",
    requires=None,
    restart_policy=None,
    restart_sec=None,
    separator="-",
    start_timeout=None,
    stop_timeout=None,
    use_name=False,
    wants=None,
    user=None,
):
    """
    Generate a systemd unit for a container or pod.

    ref
        The container/pod name or ID to generate.

    add_env
        List of additional environment variables to set in the systemd unit files.

    new
        Create a new container instead of starting an existing one. Defaults to false.

    restart_policy
        Systemd restart-policy: ``no``, ``on-success``, ``on-failure``, ``on-abnormal``,
        ``on-watchdog``, ``on-abort``, ``always``.

        Defaults to ``on-failure`` (Podman API default).

    restart_sec
        Configures the time to sleep before restarting a service.
        Defaults to ``0`` (Podman API default).

    start_timeout
        Start timeout in seconds.
        Defaults to ``0`` (Podman API default).

    stop_timeout
        Stop timeout in seconds.
        Defaults to ``10`` (Podman API default).

    after
        Systemd ``After`` list for the container or pod.

    requires
        Systemd ``Requires`` list for the container or pod.

    wants
        Systemd ``Wants`` list for the container or pod.

    container_prefix
        Systemd unit name prefix for containers. Defaults to ``container``.

    pod_prefix
        Systemd unit name prefix for pods. Defaults to ``pod``.

    separator
        Systemd unit name separator between name/id and prefix. Defaults to ``-``.

    use_name
        Use container/pod names instead of IDs. Defaults to false.

    header
        Generate a header including the Podman version and the timestamp.
        Defaults to false.

    user
        Call Podman running under this user account.
    """
    payload = {}
    for arg, param in (
        (add_env, "additionalEnvVariables"),
        (new, "new"),
        (restart_policy, "restartPolicy"),
        (restart_sec, "restartSec"),
        (start_timeout, "startTimeout"),
        (stop_timeout, "stopTimeout"),
        (after, "after"),
        (requires, "requires"),
        (wants, "wants"),
        (container_prefix, "containerPrefix"),
        (pod_prefix, "podPrefix"),
        (separator, "separator"),
        (use_name, "useName"),
        (header, "noHeader"),
    ):
        if arg is not None:
            payload[param] = arg if param != "noHeader" else not arg
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            response = client.containers.client.get(
                f"generate/{ref}/systemd", params=payload
            )
            response.raise_for_status()
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return response.json()


def image_exists(image, user=None):
    """
    Check whether an image exists locally.

    image
        The image to check for.

    user
        Check Podman running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.images.exists(image)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def images(name=None, all=False, user=None):  # pylint: disable=redefined-builtin
    """
    List local images.

    name
        Only show images belonging to this repository name.

    all
        Show intermediate image layers. Defaults to false.

    user
        List images pulled under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = [x.attrs for x in client.images.list(name=name, all=all)]
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def info(user=None):
    """
    Returns information on Podman service.

    user
        Check Podman running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.system.info()
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def inspect(container, user=None):
    """
    Inspect a container.

    container
        Name or ID of the container to inspect.

    user
        Inspect a container running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            container = client.containers.get(container)
            res = container.inspect()
    except NotFound as err:
        raise CommandExecutionError(
            f"The container {container} does not exist"
        ) from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def kill(container, signal=None, user=None):
    """
    Send a signal to a running container.

    container
        Name or ID of the container to send the signal to.

    signal
        Signal to send.

    user
        Send a signal to a container running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            container = client.containers.get(container)
            res = container.kill(signal)
    except NotFound as err:
        raise CommandExecutionError(
            f"The container {container} does not exist"
        ) from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def kill_pod(pod, signal=None, user=None):
    """
    Send a signal to a running pod.

    pod
        Name or ID of the pod to send the signal to.

    signal
        Signal to send.

    user
        Send a signal to a pod running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            pod = client.pods.get(pod)
            res = pod.kill(signal)
    except NotFound as err:
        raise CommandExecutionError(f"The pod {pod} does not exist") from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def logs(
    container,
    stdout=True,
    stderr=True,
    timestamps=False,
    tail=None,
    since=None,
    until=None,
    user=None,
):
    """
    Get logs from a container.

    container
        Name or ID of the container to get the logs from.

    stdout
        Include stdout. Defaults to true.

    stderr
        Include stderr. Defaults to true.

    timestamps
        Show timestamps in output. Defaults to false.

    tail
        Only output the last <n> lines.

    since
        Show logs since a given epoch only.

    until
        Show logs up to a given epoch only.

    user
        Get logs from a container running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            container = client.containers.get(container)
            res = container.logs(
                stdout=stdout,
                stderr=stderr,
                timestamps=timestamps,
                tail=tail,
                since=since,
                until=until,
            )
    except NotFound as err:
        raise CommandExecutionError(
            f"The container {container} does not exist"
        ) from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def network_exists(network, user=None):
    """
    Check whether a network exists.

    network
        The network to check for.

    user
        Check Podman running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.networks.exists(network)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def networks(
    names=None, ids=None, driver=None, label=None, typ=None, plugin=None, user=None
):
    """
    List networks.

    names
        List of names to filter by.

    ids
        List of ids to filter by.

    driver
        Matches a network's driver. Only ``bridge`` is supported.

    label
        Filter by labels. Format: Either ``key``, ``key=value`` or a list of such.

    typ
        Filter by network typ. Allowed: ``custom``, ``builtin``.

    plugin
        Matches CNI plugins included in a network. Allowed: ``bridge``, ``portmap``,
        ``firewall``, ``tuning``, ``dnsname``, ``macvlan``.

    user
        List containers for this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.
    """
    filters = {}
    if names is not None:
        if not isinstance(names, list):
            names = [names]
        filters["names"] = names
    if ids is not None:
        if not isinstance(ids, list):
            ids = [ids]
        filters["ids"] = ids
    if driver is not None:
        filters["driver"] = driver
    if label is not None:
        filters["label"] = label
    if typ is not None:
        filters["type"] = typ
    if plugin is not None:
        filters["plugin"] = plugin
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = [x.attrs for x in client.networks.list(filters=filters)]
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def pause(container, user=None):
    """
    Pause a running container.

    container
        Name or ID of the container to pause.

    user
        Pause a container running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            container = client.containers.get(container)
            if container.status != "running":
                raise CommandExecutionError("Container is not running")
            res = container.pause()
    except NotFound as err:
        raise CommandExecutionError(
            f"The container {container} does not exist"
        ) from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def pause_pod(pod, user=None):
    """
    Pause a running pod.

    pod
        Name or ID of the pod to pause.

    user
        Pause a pod running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            pod = client.pods.get(pod)
            res = pod.pause()
    except NotFound as err:
        raise CommandExecutionError(f"The pod {pod} does not exist") from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def ping(user=None):
    """
    Check Podman API service status.

    user
        Check Podman running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.system.ping()
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def pod_exists(pod, user=None):
    """
    Check whether a pod exists.

    pod
        The pod name or ID to check for.

    user
        Check Podman running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.pods.exists(pod)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def prune(user=None):
    """
    Delete stopped containers.

    user
        Prune containers under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.containers.prune()
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def prune_images(user=None):
    """
    Delete unused images.

    user
        Prune images under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.images.prune()
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    except TypeError as err:
        # Workaround a bug in the podman API/library
        if "'NoneType' object is not iterable" in str(err):
            return {"ImagesDeleted": [], "SpaceReclaimed": 0}
        raise
    return res


def prune_networks(user=None):
    """
    Delete unused networks.

    user
        Prune networks under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.networks.prune()
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def prune_pods(user=None):
    """
    Delete stopped pods.

    user
        Prune pods under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.pods.prune()
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def prune_volumes(user=None):
    """
    Delete unused volumes.

    user
        Prune volumes under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.volumes.prune()
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def pods(user=None):
    """
    List pods.

    user
        List pods for this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = [x.attrs for x in client.pods.list()]
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def ps(all=False, user=None):  # pylint: disable=redefined-builtin
    """
    List containers.

    all
        If false, only show running containers. Defaults to false.

    user
        List containers for this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = [x.attrs for x in client.containers.list(all=all)]
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def pull(image, tag=None, all_tags=False, platform=None, user=None):
    """
    Pull an image from a container registry.

    image
        The image to pull. Tags can be specified as usual (``<image>:<tag>``)
        or in the ``tag`` argument.

    tag
        Image tag to pull. Defaults to ``latest``.

    all_tags
        Pull all image tags from registry. Defaults to false.

    platform
        Platform in the format os[/arch[/variant]].

    user
        Pull the image for this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.
    """
    kwargs = {}
    if platform is not None:
        kwargs["platform"] = platform
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.images.pull(image, tag=tag, all_tags=all_tags, **kwargs)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res.attrs["Labels"]


def remove_network(network, force=False, user=None):
    """
    Remove a network.

    network
        Name of the network to delete.

    force
        Remove network and any associated containers.

    user
        Remove a network created under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.images.remove(network, force=force)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def remove_pod(pod, force=False, user=None):
    """
    Remove a pod.

    pod
        Name or ID of the pod to delete.

    force
        Stop and delete all containers in pod before deleting pod.

    user
        Remove a pod created under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.pods.remove(pod, force=force)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def remove_secret(secret, user=None):
    """
    Remove a secret.

    secret
        Name or ID of the secret to delete.

    user
        Remove a secret created under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.secrets.remove(secret)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def remove_volume(volume, force=False, user=None):
    """
    Remove a volume.

    volume
        Name or ID of the volume to delete.

    force
        Force deletion of in-use volume. Defaults to false.

    user
        Remove a volume created under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.volumes.remove(volume, force=force)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def restart(container, timeout=None, user=None):
    """
    Restart an existing container.

    container
        Name or ID of the container to restart.

    timeout
        Seconds to wait for container to stop before killing container.

    user
        Restart a container existing under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            container = client.containers.get(container)
            res = container.restart(timeout=timeout)
    except NotFound as err:
        raise CommandExecutionError(
            f"The container {container} does not exist"
        ) from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def restart_pod(pod, user=None):
    """
    Restart an existing pod.

    pod
        Name or ID of the pod to restart.

    user
        Restart a pod existing under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            pod = client.pods.get(pod)
            res = pod.restart()
    except NotFound as err:
        raise CommandExecutionError(f"The pod {pod} does not exist") from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def rm(container, volumes=False, force=False, user=None):
    """
    Remove a container.

    container
        Name or ID of the container to delete.

    volumes
        Delete associated volumes as well. Defaults to false.

    force
        Kill a running container before deleting. Defaults to false.

    user
        Remove a rootless container created under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.containers.remove(container, v=volumes, force=force)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def rmi(image, force=False, user=None):
    """
    Remove an image.

    image
        Name of the image to delete.

    force
        Delete image even if in use.

    user
        Remove an image pulled under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.images.remove(image, force=force)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def run(
    image, command=None, remove=False, stdout=True, stderr=False, user=None, **kwargs
):
    """
    Run a container.

    image
        The image to base the container on.

    command
        Command to run in the container.

    remove
        Delete the container after the container's processes have finished. Defaults to False.

    stdout
        Include stdout output in the return. Defaults to True.

    stderr
        Include stderr output in the return. Defaults to False.

    user
        Run a rootless container under this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.

    kwargs
        Keyword arguments that are passed to the ``create`` method of the
        ContainersManager instance.

        https://github.com/containers/podman-py/blob/main/podman/domain/containers_create.py
    """
    is_retry = kwargs.pop("is_retry", False)
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.containers.run(
                image, command=command, remove=remove, **_filter_kwargs(kwargs)
            )
    except (APIError, PodmanError) as err:
        # https://github.com/containers/podman-py/issues/231
        if not is_retry and isinstance(err, APIError) and "image not known" in str(err):
            pull(image, user=user)
            return run(
                image,
                command=command,
                remove=remove,
                stdout=stdout,
                stderr=stderr,
                user=user,
                is_retry=True,
                **kwargs,
            )
        try:
            msg = str(err) + "\n\n" + b"\n".join(err.stderr).decode()
        except (AttributeError, UnicodeDecodeError):
            msg = str(err)
        raise CommandExecutionError(f"{type(err).__name__}: {msg}") from err
    if kwargs.get("detach"):
        return res.id
    return res or True


def secret_exists(secret, user=None):
    """
    Check whether a secret exists.

    secret
        The secret name or ID to check for.

    user
        Check Podman running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.secrets.exists(secret)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def secrets(user=None):
    """
    List secrets.

    user
        List secrets for this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = [x.attrs for x in client.secrets.list()]
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def start(container, user=None):
    """
    Start an existing container.

    container
        Name or ID of the container to start.

    user
        Start a container existing under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            container = client.containers.get(container)
            if container.status == "running":
                raise CommandExecutionError("Container is already running")
            res = container.start()
    except NotFound as err:
        raise CommandExecutionError(
            f"The container {container} does not exist"
        ) from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def start_pod(pod, user=None):
    """
    Start an existing pod.

    pod
        Name or ID of the pod to start.

    user
        Start a pod existing under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            pod = client.pods.get(pod)
            res = pod.start()
    except NotFound as err:
        raise CommandExecutionError(f"The pod {pod} does not exist") from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def stop(container, timeout=None, user=None):
    """
    Stop a running container.

    container
        Name or ID of the container to stop.

    timeout
        Seconds to wait for container to stop before killing container.

    user
        Stop a container running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            container = client.containers.get(container)
            if container.status != "running":
                raise CommandExecutionError("Container is already stopped")
            res = container.stop(timeout=timeout)
    except NotFound as err:
        raise CommandExecutionError(
            f"The container {container} does not exist"
        ) from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def stop_pod(pod, timeout=None, user=None):
    """
    Stop a running pod.

    pod
        Name or ID of the pod to stop.

    timeout
        Seconds to wait for pod to stop before killing pod.

    user
        Stop a pod running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            pod = client.pods.get(pod)
            res = pod.stop(timeout=timeout)
    except NotFound as err:
        raise CommandExecutionError(f"The pod {pod} does not exist") from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def top(container, ps_args=None, user=None):
    """
    Report on running processes in the container.

    container
        Name or ID of the container to report on.

    ps_args
        Pass arguments to ``ps``.

    user
        Report on a container running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            container = client.containers.get(container)
            if container.status != "running":
                raise CommandExecutionError("Container is not running")
            res = container.top(ps_args=ps_args)
    except NotFound as err:
        raise CommandExecutionError(
            f"The container {container} does not exist"
        ) from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    rendered = []
    for process in res["Processes"]:
        rendered.append(dict(zip(res["Titles"], process)))
    return rendered


def top_pod(pod, ps_args=None, user=None):
    """
    Report on running processes in the pod.

    pod
        Name or ID of the pod to report on.

    ps_args
        Pass arguments to ``ps``.

    user
        Report on a pod running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            pod = client.pods.get(pod)
            res = pod.top(ps_args=ps_args)
    except NotFound as err:
        raise CommandExecutionError(f"The pod {pod} does not exist") from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    rendered = []
    for process in res["Processes"]:
        rendered.append(dict(zip(res["Titles"], process)))
    return rendered


def unpause(container, user=None):
    """
    Unpause a paused container.

    container
        Name or ID of the container to unpause.

    user
        Unpause a container running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            container = client.containers.get(container)
            if container.status != "paused":
                raise CommandExecutionError("Container is not paused")
            res = container.unpause()
    except NotFound as err:
        raise CommandExecutionError(
            f"The container {container} does not exist"
        ) from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def unpause_pod(pod, user=None):
    """
    Unpause a paused pod.

    pod
        Name or ID of the pod to unpause.

    user
        Unpause a pod running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            pod = client.pods.get(pod)
            res = pod.unpause()
    except NotFound as err:
        raise CommandExecutionError(f"The pod {pod} does not exist") from err
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res or True


def version(user=None):
    """
    Get version information from service.

    user
        Check Podman running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.system.version()
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def volume_exists(volume, user=None):
    """
    Check whether a volume exists.

    volume
        The volume name or ID to check for.

    user
        Check Podman running under this user account.
    """
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = client.volumes.exists(volume)
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res


def volumes(driver=None, label=None, name=None, user=None):
    """
    List volumes.

    driver
        Filter listed volumes by their driver.

    label
        Filter listed volumes by label and/or value [Dict[str, str]].

    name
        Filter listed volumes by name.

    user
        List volumes for this user account. Requires the Podman
        socket to run for this user, which usually requires lingering enabled.
    """
    filters = {}
    if driver is not None:
        filters["driver"] = driver
    if label is not None:
        filters["label"] = label
    if name is not None:
        filters["name"] = name
    try:
        with PodmanClient(base_url=_find_podman_sock(user=user)) as client:
            res = [x.attrs for x in client.volumes.list(filters=filters)]
    except (APIError, PodmanError) as err:
        raise CommandExecutionError(f"{type(err).__name__}: {err}") from err
    return res
