"""
Install and manage container compositions with ``podman``.

This module is intended to be used akin ``docker-compose``/
``podman-compose`` to deploy small stacks on a single server
easily and with rootless support (e.g. homelab). It takes care of

* generating podman systemd units from docker-compose.yml files
* managing their state

It exists because writing states that try to account for
several different configurations tend to get ugly fast
(pod vs separate containers, rootful vs rootless, reloading
after configuration change).

Configuration options:

compose.containers_base
    If composition/project is just a name, use this directory as the
    base to autodiscover projects. Defaults to ``/opt/containers``.
    Example: project=gitea -> ``/opt/containers/gitea/docker-compose.yml``

compose.default_to_dirowner
    If user is unspecified, try to guess the user running the project
    by looking up the dir owner. Defaults to True.

compose.default_pod_prefix
    By default, prefix service units for composition pods with this
    string. Defaults to empty (podman-compose still prefixes the
    pods themselves with ``pod_`` currently).

compose.default_container_prefix
    By default, prefix service units for containers with this
    string. Defaults to empty.

Todo:
    * import/export Kubernetes YAML files
"""

import logging
import re
import shlex
from functools import wraps
from pathlib import Path

import salt.utils.hashutils
import salt.utils.json
import salt.utils.path
import salt.utils.yaml
from salt.exceptions import CommandExecutionError, SaltInvocationError

# try:
#     import podman_compose
#     HAS_COMPOSE = True
# except ImportError:
#     HAS_COMPOSE = False

log = logging.getLogger(__name__)

VALID_UNIT_TYPES = (
    "service",
    "socket",
    "device",
    "mount",
    "automount",
    "swap",
    "target",
    "path",
    "timer",
)

containers_base = "/opt/containers"
default_to_dirowner = True
default_pod_prefix = ""
default_container_prefix = ""


def __init__(opts):
    global containers_base
    global default_to_dirowner
    global default_pod_prefix
    global default_container_prefix
    containers_base = opts.get("compose.containers_base", containers_base)
    default_to_dirowner = opts.get("compose.default_to_dirowner", default_to_dirowner)
    default_pod_prefix = opts.get("compose.default_pod_prefix", default_pod_prefix)
    default_container_prefix = opts.get(
        "compose.default_container_prefix", default_container_prefix
    )


def _which_podman():
    return salt.utils.path.which("podman")


def _which_podman_compose():
    # this will disregard user-installed podman-compose
    return salt.utils.path.which("podman-compose")


def _needs_compose(func):
    @wraps(func)
    def needs_compose(*args, **kwargs):
        if not _which_podman_compose():
            raise SaltInvocationError(
                "Running this function requires podman_compose library. "
                "Make sure it is importable by Salt."
            )
        return func(*args, **kwargs)

    return needs_compose


def __virtual__():
    """
    Only load the module if podman is installed
    """

    if _which_podman():
        return True
    return (
        False,
        "The compose execution module cannot be loaded: podman is not installed.",
    )


def _run(
    bin_path,
    command,
    args=None,
    cmd_args=None,
    params=None,
    runas=None,
    cwd=None,
    json=False,
    raise_error=True,
    expect_error=False,
    env=None,
):
    """
    Generic helper for running some console commands.
    json switch works for podman/podman-compose
    """

    args = args or []
    cmd_args = cmd_args or []

    if json:
        cmd_args.append(("format", "json"))

    # https://bugs.python.org/issue47002
    # podman-compose uses argparse, which has problems with --opt '--something'
    # thus use --opt='--something'
    args = _parse_args(args, include_equal=True)
    cmd_args = _parse_args(cmd_args, include_equal=True)
    cmd = [bin_path] + args + [command] + cmd_args

    if params is not None:
        cmd += ["--"] + params

    log.info(
        "Running command%s: %s", f" as user {runas}" if runas else "", " ".join(cmd)
    )

    out = __salt__["cmd.run_all"](
        " ".join(cmd),
        cwd=cwd,
        env=env,
        runas=runas,
        ignore_retcode=expect_error,
    )

    if not expect_error and raise_error and out["retcode"]:
        raise CommandExecutionError(
            f"Failed running {bin_path} {command}.\n"
            f"stderr: {out['stderr']}\n"
            f"stdout: {out['stdout']}"
        )

    if not out["retcode"] and json:
        out["parsed"] = salt.utils.json.loads(out["stdout"])
    return out


def _parse_args(args, include_equal=False):
    """
    Helper for parsing lists of arguments into a flat list.
    """
    tpl = "--{}={}" if include_equal else "--{} {}"
    return [tpl.format(*arg) if isinstance(arg, tuple) else f"--{arg}" for arg in args]


def _convert_args(args):
    """
    Helper for converting lists of arguments containing dicts to lists
    of arguments containing tuples
    """

    converted = []

    for arg in args:
        if isinstance(arg, dict):
            arg = next(iter(arg.items()))
        converted.append(arg)

    return converted


def _podman(
    command,
    args=None,
    cmd_args=None,
    params=None,
    runas=None,
    cwd=None,
    json=False,
    raise_error=True,
    expect_error=False,
    env=None,
    bin_path=None,
):
    """
    Helper for running arbitary ``podman`` commands.
    """

    bin_path = bin_path or "podman"

    return _run(
        bin_path,
        command,
        args=args,
        cmd_args=cmd_args,
        params=params,
        runas=runas,
        cwd=cwd,
        json=json,
        raise_error=raise_error,
        expect_error=expect_error,
        env=env,
    )


def _podman_compose(
    command,
    args=None,
    cmd_args=None,
    params=None,
    runas=None,
    cwd=None,
    json=False,
    raise_error=True,
    expect_error=False,
    env=None,
    bin_path=None,
):
    """
    Helper for running arbitary ``podman-compose`` commands.

    Note for developers:
        The program is written in Python, but cannot easily used as a library
        since a) the whole script is monolithic b) multithreading might be difficult (?).
    """

    bin_path = bin_path or "podman-compose"

    return _run(
        bin_path,
        command,
        args=args,
        cmd_args=cmd_args,
        params=params,
        runas=runas,
        cwd=cwd,
        json=json,
        raise_error=raise_error,
        expect_error=expect_error,
        env=env,
    )


def _systemctl(
    command,
    args=None,
    cmd_args=None,
    params=None,
    runas=None,
    cwd=None,
    raise_error=True,
    expect_error=False,
    env=None,
):
    """
    Helper for running arbitary ``systemctl`` commands related to podman services.
    """

    args = args or []
    env = env or []

    if runas:
        uid = _user_info(runas, "uid")
        xdg_runtime_dir = f"/run/user/{uid}"
        dbus_session_bus = f"{xdg_runtime_dir}/bus"

        if not Path(dbus_session_bus).exists():
            raise CommandExecutionError(
                f"User {runas} does not have lingering enabled. This is required "
                "to run systemctl as a user that does not have a login session."
            )

        args = ["user"] + args
        env.append({"XDG_RUNTIME_DIR": xdg_runtime_dir})
        env.append({"DBUS_SESSION_BUS_ADDRESS": f"unix:path={dbus_session_bus}"})

    return _run(
        "systemctl",
        command,
        args=args,
        cmd_args=cmd_args,
        params=params,
        runas=runas,
        cwd=cwd,
        json=False,
        raise_error=raise_error,
        expect_error=expect_error,
        env=env,
    )


def _loginctl(command, cmd_args=None, params=None, expect_error=False):
    """
    Basic helper for running some ``loginctl`` commands (specifically
    related to lingering).
    """

    return _run(
        "loginctl", command, cmd_args=cmd_args, params=params, expect_error=expect_error
    )


def _journalctl(
    unit,
    runas=None,
    raise_error=True,
    expect_error=False,
    env=None,
):
    """
    Helper for running arbitary ``systemctl`` commands related to podman services.
    """

    args = []
    env = env or []

    if runas:
        uid = _user_info(runas, "uid")
        xdg_runtime_dir = f"/run/user/{uid}"
        dbus_session_bus = f"{xdg_runtime_dir}/bus"

        if not Path(dbus_session_bus).exists():
            raise CommandExecutionError(
                f"User {runas} does not have lingering enabled. This is required "
                "to run systemctl as a user that does not have a login session."
            )

        args = ["user", "reverse"] + [("unit", unit)] + args
        env.append({"XDG_RUNTIME_DIR": xdg_runtime_dir})
        env.append({"DBUS_SESSION_BUS_ADDRESS": f"unix:path={dbus_session_bus}"})

    return _run(
        "journalctl",
        "",
        args=args,
        runas=runas,
        raise_error=raise_error,
        expect_error=expect_error,
        env=env,
    )


def _user_info(user, var=""):
    """
    Helper for inspecting a user account.
    """

    user_info = __salt__["user.info"](user)

    if not user_info:
        raise SaltInvocationError(
            f"Could not find user '{user}'. Does the account exist?"
        )
    if not var:
        return user_info

    val = user_info.get(var)
    if val is None:
        raise SaltInvocationError(
            f"Could not find {var} of user '{user}'. Make sure the account exists."
        )

    return val


def service_dir(user=None):
    """
    Returns the path of the directory service units should be
    installed in.


    CLI Example:

    .. code-block:: bash

        salt '*' compose.service_dir gitea

    user
        The user account to return the service directory for.
        If unset, defaults to root.
    """
    if user is None:
        # This module generally assumes Salt is running as root
        return str(Path("/") / "etc" / "systemd" / "system")

    home = _user_info(user, "home")
    return str(Path(home) / ".config" / "systemd" / "user")


def _canonical_unit_name(name):
    """
    Build a canonical unit name treating unit names without one
    of the valid suffixes as a service.
    This function is modified from the official systemd_service module.
    """
    if not isinstance(name, str):
        name = str(name)
    if any(name.endswith(suffix) for suffix in VALID_UNIT_TYPES):
        return name
    return f"{name}.service"


def _check_available(name, user=None):
    """
    Returns boolean telling whether or not the named service is available
    This function is modified from the official systemd_service module.
    """

    _status = _systemctl_status(name, user)

    # Since version 231, unknown services return an exit status of 4.
    # This has been out for a long time, so for this module
    # I'm not bothering to support old versions.
    # See: https://github.com/systemd/systemd/pull/3385
    # Also: https://github.com/systemd/systemd/commit/3dced37
    return 0 <= _status["retcode"] < 4


def _check_for_unit_changes(name, user=None):
    """
    Check for modified/updated unit files, and run a daemon-reload if any are
    found.
    This function is modified from the official systemd_service module.
    """

    contextkey = f"compose._check_for_unit_changes.{name}"
    if user is not None:
        contextkey += f".{user}"

    if contextkey not in __context__:
        if _untracked_custom_unit_found(name, user) or _unit_file_changed(name, user):
            systemctl_reload()
        # Set context key to avoid repeating this check
        __context__[contextkey] = True


def _clear_context():
    """
    Remove context
    This function is modified from the official systemd_service module.
    """
    # Using list() here because modifying a dictionary during iteration will
    # raise a RuntimeError.
    for key in list(__context__):
        try:
            if key.startswith("compose._systemctl_status."):
                __context__.pop(key)
        except AttributeError:
            continue


def _systemctl_status(name, user=None):
    """
    Helper function which leverages __context__ to keep from running 'systemctl
    status' more than once.
    This function is modified from the official systemd_service module.
    """

    contextkey = f"compose._systemctl_status.{name}"
    if user is not None:
        contextkey += f".{user}"

    if contextkey not in __context__:
        # expect_error is necessary because systemctl returns with
        # retcode 3 for inactive units
        # https://refspecs.linuxbase.org/LSB_5.0.0/LSB-Core-generic/LSB-Core-generic/iniscrptact.html
        __context__[contextkey] = _systemctl(
            "status", params=[name], runas=user, expect_error=True
        )
    return __context__[contextkey]


def _untracked_custom_unit_found(name, user=None):
    """
    If the passed service name is not available, but a unit file exist in
    /etc/systemd/system, return True. Otherwise, return False.
    This function is modified from the official systemd_service module.
    """
    services = service_dir(user)
    unit_path = Path(services) / _canonical_unit_name(name)
    return unit_path.exists() and not _check_available(name, user)


def _unit_file_changed(name, user=None):
    """
    Returns True if systemctl reports that the unit file has changed, otherwise
    returns False.
    This function is modified from the official systemd_service module.
    """
    sctl_status = _systemctl_status(name, user)["stdout"].lower()
    return "'systemctl daemon-reload'" in sctl_status


def systemctl(
    command,
    args=None,
    cmd_args=None,
    params=None,
    user=None,
):
    """
    Run arbitrary systemctl commands. This is an extension to the
    official module, which allows executing this for a specific
    user.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.systemctl start params=[gitea.service] user=gitea

    command
        systemctl subcommand to execute

    args
        Command line options for systemctl itself to pass.

    cmd_args
        Command line options for the systemctl subcommand to pass.

    params
        Arguments to pass to the systemctl subcommand.
        @TODO naming is absolutely horrific in this module

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    return _systemctl(command, args=args, cmd_args=cmd_args, params=params, runas=user)


def systemctl_status(name, user=None):
    """
    Returns the output of systemctl status (cmd.run_all).

    CLI Example:

    .. code-block:: bash

        salt '*' compose.systemctl_status podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """
    return _systemctl_status(name, user)


def systemctl_is_enabled(unit, user=None):
    """
    Check whether a systemd unit is enabled. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.systemctl_is_enabled podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    out = _systemctl("is-enabled", params=[unit], runas=user, expect_error=True)
    return "enabled" == out["stdout"]


def systemctl_is_running(unit, user=None):
    """
    Check whether a systemd unit is running. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.systemctl_is_running podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    out = _systemctl("is-active", params=[unit], runas=user, expect_error=True)
    return 0 == out["retcode"]


def systemctl_start(unit, user=None):
    """
    Start a systemd unit. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.systemctl_start podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    _systemctl("start", params=[unit], runas=user)
    return True


def systemctl_stop(unit, user=None):
    """
    Stop a systemd unit. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.systemctl_stop podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    _systemctl("stop", params=[unit], runas=user)
    return True


def systemctl_restart(unit, user=None):
    """
    Restart a systemd unit. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.systemctl_restart podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    _systemctl("restart", params=[unit], runas=user)
    return True


def systemctl_enable(unit, user=None):
    """
    Enable a systemd unit. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.systemctl_enable podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    _systemctl("enable", params=[unit], runas=user)
    return True


def systemctl_disable(unit, user=None):
    """
    Disable a systemd unit. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.systemctl_disable podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    _systemctl("disable", params=[unit], runas=user)
    return True


def systemctl_reload(user=None):
    """
    Reloads systemd unit files. This is an extension to the
    official module, which allows executing this for a specific
    user.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.systemctl_reload gitea

    user
        The user to reload systemd units for. Defaults to
        Salt process user.
    """

    _systemctl("daemon-reload", runas=user)
    _clear_context()
    return True


def lingering_disable(user):
    """
    Disable lingering for a user.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.lingering_disable user

    user
        The user to disable lingering for.
    """

    _loginctl("disable-linger", params=[user])
    return True


def lingering_enable(user):
    """
    Enable lingering for a user.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.lingering_enable user

    user
        The user to enable lingering for.
    """

    _loginctl("enable-linger", params=[user])
    return True


def lingering_enabled(user):
    """
    Check whether lingering is enabled for a user.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.lingering_enabled user

    user
        The user to check lingering status for.
    """

    # need to expect error since this command fails if
    # there is no user session
    out = _loginctl("show-user", [("property", "Linger")], [user], expect_error=True)

    if out["retcode"] and "not logged in or lingering" in out["stderr"]:
        return False
    if not out["retcode"]:
        return "Linger=yes" in out["stdout"]
    raise CommandExecutionError(f"Failed running loginctl: {out['stderr']}")


def _get_compose_hash(file):
    """
    Helper to get the hash of a compose file. It needs to normalize the data
    the same way podman-compose does to arrive at the same hash in order to
    avoid unnecessary updates.
    """

    with open(file, "r") as f:
        definitions = salt.utils.yaml.load(f)

    if not isinstance(definitions, dict) or "services" not in definitions:
        raise CommandExecutionError(f"Compose file {file} is invalid.")

    # need to normalize the data
    try:
        import os

        import podman_compose

        definitions = podman_compose.normalize(definitions)
        definitions = podman_compose.rec_subs(definitions, dict(os.environ))
    except ImportError:
        # This is a very condensed variant of podman-compose functionality
        # and tries to avoid some common cases where the resulting hashes might differ.
        # This does not do variable substitution, but it removes escape chars.

        for srv in definitions["services"]:
            for key in ("env_file", "security_opt", "volumes"):
                if key not in srv:
                    continue
                srv[key] = [srv[key]] if isinstance(srv[key], str) else srv[key]

        def unescape(val):
            if isinstance(val, dict):
                val = {k: unescape(v) for k, v in val.items()}
            elif isinstance(val, str):
                if "$$" in val:
                    val = val.replace("$$", "$")
            elif hasattr(val, "__iter__"):
                val = [unescape(i) for i in val]
            return val

        definitions = unescape(definitions)

    return (
        salt.utils.hashutils.sha256_digest(
            salt.utils.json.dumps(definitions, separators=(",", ":"))
        ),
        definitions,
    )


def has_changes(
    composition,
    status_only=False,
    skip_removed=False,
    project_name=None,
    container_prefix=None,
    pod_prefix=None,
    separator=None,
    user=None,
):
    """
    Check whether a container composition has changed since the last application.

    This currently does not account for merged definitions from multiple files,
    including env files (afaics podman-compose does not do the latter either).

    This also does not check for pod-specific arguments since they are not part
    of the definitions.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.has_changes /opt/gitea/docker-compose.yml

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    status_only
        Only return boolean result instead of map ``{changed: [], missing: []}``.
        Defaults to False.

    skip_removed
        If a container has been removed from a composition, but is still running,
        do not count that as changes. Defaults to False.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    pod_prefix
        Unit name prefix for pods. Defaults to empty
        (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    missing = list_missing_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    ret = {"changed": [], "missing": missing}

    if status_only and missing["pods"] or missing["containers"]:
        return True

    containers = ps(project_name, user=user)

    # semantically different:
    #   running containers vs unit files
    #   but this assumes everything is managed with this module,
    #   so all running containers have been generated from the files
    #   so not a problem
    #
    # 1) check if found containers / units are up to date
    # 2) check if all necessary unit files are installed

    if not containers:
        installed_units = list_installed_units(
            composition,
            project_name=project_name,
            pod_prefix=pod_prefix,
            container_prefix=container_prefix,
            separator=separator,
            user=user,
        )
        for srv in installed_units["containers"]:
            # this checks the service files themselves for ephemeral services
            containers.append(inspect_unit(srv, user=user, podman_ps_if_running=False))

    if not containers:
        if status_only:
            # this should be False always since there is a check above
            # it should also never hit because that would imply there
            # are no services defined inside the file
            return bool(missing["pods"] or missing["containers"])

        return ret

    new_hash, definitions = _get_compose_hash(composition)

    for cnt in containers:
        config_hash = cnt["Labels"].get("io.podman.compose.config-hash")

        if not config_hash:
            raise CommandExecutionError(
                f"Could not find configuration hash of container {cnt['Id'][:12]}. "
                "Was it created by podman-compose?"
            )

        if config_hash != new_hash:
            if (
                not skip_removed
                or cnt["Labels"].get("com.docker.compose.service")
                in definitions["services"]
            ):
                ret["changed"].append(
                    cnt["Labels"].get("PODMAN_SYSTEMD_UNIT", cnt["Id"])
                )

    # This currently does not check for changes in pod service files @TODO

    if status_only:
        return bool(
            ret["changed"] or ret["missing"]["pods"] or ret["missing"]["containers"]
        )
    return ret


def list_outdated_units(
    composition,
    project_name=None,
    container_prefix=None,
    pod_prefix=None,
    separator=None,
    user=None,
):
    """
    Tries to discover installed service units for this composition
    and check if they are in sync with the definitions.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.list_outdated_units /opt/gitea/docker-compose.yml

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    pod_prefix
        Unit name prefix for pods. Defaults to empty
        (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    installed_units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    new_hash, definitions = _get_compose_hash(composition)
    changed = []

    for srv in installed_units["containers"]:
        cnt = inspect_unit(srv, user=user, podman_ps_if_running=False)
        config_hash = cnt["Labels"].get("io.podman.compose.config-hash")

        if not config_hash:
            raise CommandExecutionError(
                f"Could not find configuration hash of container {cnt['Id'][:12]}. "
                "Was it created by podman-compose?"
            )

        if config_hash != new_hash:
            if (
                cnt["Labels"].get("com.docker.compose.service")
                in definitions["services"]
            ):
                changed.append(cnt["Labels"]["PODMAN_SYSTEMD_UNIT"])

    # @TODO does not check for changed pod creation arguments atm
    # pod_args = inspect_unit(pod_srv, user=user)

    # does not need status_only since an empty list evaluates to false
    return changed


def _list_units(
    composition,
    project_name=None,
    container_prefix=None,
    pod_prefix=None,
    separator=None,
    user=None,
):
    """
    Helper that lists expected service units and their paths.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    if (container_prefix or pod_prefix) and separator is None:
        separator = "-"
    else:
        separator = ""

    with open(composition, "r") as f:
        definitions = salt.utils.yaml.load(f)

    service_names = []

    for srv, conf in definitions["services"].items():
        replicas = int(conf.get("deploy", {}).get("replicas", 1))
        for num in range(1, replicas + 1):
            name_default = f"{project_name}_{srv}_{num}"

            if 1 == num:
                name = conf.get("container_name", name_default)
            else:
                name = name_default

            service_names.append(f"{container_prefix}{separator}{name}")

    # podman-compose currently automatically prefixes pods with "pod_"
    # this was not the case in 0.* versions
    pod = f"{pod_prefix}{separator}pod_{project_name}"

    return pod, service_names


def _is_unit_installed(service, user):
    """
    Helper for checking if a unit file exists.
    """

    sdir = Path(service_dir(user))
    if not sdir.exists():
        return False, None

    path = sdir / (_canonical_unit_name(service))
    return path.exists(), str(path)


def list_missing_units(
    composition,
    status_only=False,
    project_name=None,
    container_prefix=None,
    pod_prefix=None,
    should_have_pod=None,
    separator=None,
    user=None,
):
    """
    Lists missing service units for this composition.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.list_missing_units /opt/gitea/docker-compose.yml

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    status_only
        Only return boolean result instead of map ``{pods: [], containers: []}``.
        Defaults to False.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    pod_prefix
        Unit name prefix for pods. Defaults to empty
        (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    should_have_pod
        Whether the composition should have a pod service. Defaults to True.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    pod_name, service_names = _list_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    containers = {}
    pods = {}

    for service in service_names:
        is_installed, path = _is_unit_installed(service, user)
        if not is_installed:
            containers[service] = path

    is_installed, path = _is_unit_installed(pod_name, user)
    if not is_installed and should_have_pod:
        pods[pod_name] = path

    if status_only:
        return bool(containers or pods)

    return {"containers": containers, "pods": pods}


def list_installed_units(
    composition,
    status_only=False,
    project_name=None,
    container_prefix=None,
    pod_prefix=None,
    separator=None,
    user=None,
):
    """
    Tries to discover installed service units for this composition.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.list_installed_units /opt/gitea/docker-compose.yml

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    status_only
        Only return boolean result instead of map ``{pods: [], containers: []}``.
        Defaults to False.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    pod_prefix
        Unit name prefix for pods. Defaults to empty
        (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    pod_name, service_names = _list_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    containers = {}
    pods = {}

    for service in service_names:
        is_installed, path = _is_unit_installed(service, user)
        if is_installed:
            containers[service] = path

    is_installed, path = _is_unit_installed(pod_name, user)
    if is_installed:
        pods[pod_name] = path

    if status_only:
        return bool(containers or pods)

    return {"containers": containers, "pods": pods}


def inspect_unit(unit, user=None, podman_ps_if_running=False):
    """
    Tries to parse an installed service file to an output similar to
    ``podman ps``. This is handy when ephemeral containers are used
    and the services are not running.

    unit
        The name of the unit to inspect.

    user
        The user that runs the unit. Defaults to Salt process user.
        This cannot autodiscover the owner since it does not
        know about it.

    podman_ps_if_running
        For ephemeral containers, return the output of ``podman ps``
        if the service is running instead of parsing the unit.
        Defaults to False.
    """

    unit = _canonical_unit_name(unit)
    unit_file = Path(service_dir(user)) / unit
    if not unit_file.exists():
        raise SaltInvocationError(f"File '{unit_file}' does not exist.")
    contents = unit_file.read_text()

    def parse_arguments(args):
        parsed = {"options": {}, "params": []}
        args = shlex.split(args)
        # newline chars mess up the "logic"
        args = [x for x in args if x not in ["\n"]]
        cur, num = 0, len(args)
        options_finished = False

        while cur < num:
            if not args[cur].startswith("-") or options_finished:
                options_finished = True
                parsed["params"].append(args[cur])
                cur += 1
                continue

            arg = args[cur].lstrip("-")
            val = True

            if cur + 1 < num and not args[cur + 1].startswith("-"):
                cur += 1
                val = args[cur]
            elif "=" in arg:
                arg, val = arg.split("=", 1)

            if arg in parsed["options"]:
                if not isinstance(parsed["options"][arg], list):
                    parsed["options"][arg] = [parsed["options"][arg]]
                parsed["options"][arg].append(val)
            else:
                parsed["options"][arg] = val
            cur += 1
        return parsed

    # If the container is not created by the service,
    # it has to exist in podman. Better to let it handle ps.

    non_ephemeral = re.findall(
        r"^ExecStart=[a-z\/]+podman start([^\n]*(?:\n+(?!\w+=|[\[#;])[^\n]+)+|[^\n]+)",
        contents,
        flags=re.MULTILINE,
    )
    if non_ephemeral:
        args = parse_arguments(non_ephemeral[0])
        return ps(name=args["params"][0])

    pod = re.findall(
        r"^ExecStartPre=[a-z\/]+podman pod create(.*)", contents, flags=re.MULTILINE
    )
    if pod:
        # @TODO better parsing? flags are returned as True (python)
        return parse_arguments(pod[0])

    cnt = re.findall(
        r"^ExecStart=[a-z\/]+podman run([^\n]*(?:\n+(?!\w+=|[\[#;])[^\n]+)+|[^\n]+)",
        contents,
        flags=re.MULTILINE,
    )
    if not cnt:
        raise CommandExecutionError(
            "Failed parsing unit {unit}. Was it created by podman?"
        )

    if podman_ps_if_running:
        out = ps(systemd_unit=unit, user=user)
        if out:
            return out

    args = parse_arguments(cnt[0])

    parsed = {
        # bool(args["options"].get("replace")) not needed
        "AutoRemove": True,
        "Command": [],
        "CreatedAt": "",
        "Exited": None,
        "ExitedAt": None,
        "ExitCode": None,
        "Id": None,
        "Image": args["params"][0],
        "ImageID": None,
        "IsInfra": False,
        "Labels": {
            var: val
            for label in args["options"].get("label", [])
            for var, val in [label.split("=", 1)]
        },
        "Mounts": [],
        "Names": [],
        "Namespaces": {},
        "Networks": [],
        "Pid": None,
        "Pod": None,
        "PodName": "",
        "Ports": [],
        "Size": None,
        "StartedAt": None,
        "State": None,
        "Status": None,
        "Created": None,
    }

    parsed["Labels"]["PODMAN_SYSTEMD_UNIT"] = unit

    if "v" in args["options"]:
        vols = args["options"]["v"]
        if not isinstance(vols, list):
            vols = [vols]
        parsed["Mounts"] = [vol.split(":", 1)[1] for vol in vols]

    if "net" in args["options"]:
        nets = args["options"]["net"]
        if not isinstance(nets, list):
            nets = [nets]
        parsed["Networks"] = nets

    return parsed


@_needs_compose
def install(
    composition,
    project_name=None,
    create_pod=None,
    pod_args=None,
    pod_args_override_default=False,
    podman_create_args=None,
    remove_orphans=True,
    force_recreate=False,
    build=False,
    build_args=None,
    pull=False,
    user=None,
    ephemeral=True,
    restart_policy=None,
    restart_sec=None,
    stop_timeout=None,
    service_overrides=None,
    pod_wants=True,
    enable_units=True,
    now=False,
    pod_prefix=None,
    container_prefix=None,
    separator=None,
):
    """
    Install a container composition.

    This will create the necessary resources and
    generate systemd units dedicated to managing their lifecycle.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.install gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    create_pod
        Create a pod for the composition. Defaults to True, if ``podman-compose``
        supports it. Forced on 0.*, unavailable in 1.* <= 1.0.3.

    pod_args
        List of custom arguments to ``podman pod create`` when create_pod is True.
        To support ``systemd`` managed pods, an infra container is necessary. Otherwise,
        none of the namespaces are shared by default. In summary,
        ["infra", {"share": ""}] is default.

    pod_args_override_default
        If pod_args are specified, do not add them to the default values. Defaults to False.

    podman_create_args
        List of custom arguments to ``podman create``. This can be used to pass
        options that are not exposed by podman-compose by default, e.g. userns.
        See `man 'podman-create(1)' <https://docs.podman.io/en/latest/markdown/podman-create.1.html#options>`_

    remove_orphans
        Remove containers not defined in the composition. Defaults to True.

    force_recreate
        Always recreate containers, even if their configuration and images
        have not changed. Defaults to False.
        no_recreate is currently not implemented by podman-compose.

    build
        Build images before starting containers. Defaults to False.

    build_args
        Set build-time variables for services.

    pull
        Whether to pull potential updated images before creating the container.
        Defaults to False.

    user
        Install rootless containers under this user account instead
        of rootful ones. Defaults to the composition file parent dir owner
        (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.

    ephemeral
        Create new containers on service start, remove them on stop. Defaults to True.

    restart_policy
        Unit restart policy, defaults to ``on-failure``.
        This is not taken from the compose definition @TODO

    restart_sec
        Specify systemd RestartSec. Requires at least podman v4.3.

    stop_timeout
        Unit stop timeout, defaults to 10 [s].

    service_overrides
        Override generation parameters per unit. This should be a dictionary,
        mapping the service name as specified in the compose file
        to extra parameters (dict as well).

    pod_wants
        Ensure the pod dependencies for containers are enforced with ``Wants=``
        instead of ``Requires=``. This fixes issues when restarting a single
        container that is part of a pod, e.g. when auto-update is run.
        See https://github.com/containers/podman/issues/14546.

    enable_units
        Enable the service units after installation. Defaults to True.

    now
        Start the services after installation. Defaults to False.

    pod_prefix
        Unit name prefix for pods.
        Defaults to empty (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)

    pc_pod_support = podman_compose_supports_pods(user)
    if (
        create_pod is not None
        and create_pod != pc_pod_support["supported"]
        and pc_pod_support["required"]
    ):
        log.warning(
            "Your podman-compose %s pod creation. Overriding.",
            "does not" if create_pod else "requires",
        )
        # this is actually unnecessary atm, just for consistency
        create_pod = pc_pod_support["supported"]
    elif create_pod is None:
        create_pod = pc_pod_support["supported"]

    if pod_args is not None and pc_pod_support["required"]:
        log.warning(
            "Your podman-compose does not support customization of pod creation. Overriding."
        )

    if pod_args_override_default:
        pod_args = pod_args or ["infra", {"share": ""}]
    else:
        pod_args = (pod_args or []) + ["infra", {"share": ""}]
    podman_create_args = podman_create_args or []

    args = [("file", composition), ("project-name", project_name)]
    cmd_args = ["no-start"]

    # pod settings are only available in versions >=1.0.6
    # (formerly 1.0.4 with --no-pod arg, but only .6 was actually tagged with inverse arg)
    if not pc_pod_support["required"]:
        if create_pod:
            # in versions where the choice is possible, the default is to not create a pod
            pod_args = _parse_args(_convert_args(pod_args), include_equal=True)
            if not pc_pod_support["pod_default"]:
                args.append("in-pod")
            args.append(("pod-args", "'{}'".format(" ".join(pod_args))))
        elif pc_pod_support["no_pod_switch"]:
            # 1.0.4 (unreleased) created a pod by default
            args.append("no-pod")
        elif pc_pod_support["pod_default"]:
            # The current latest code does not handle a boolean flag correctly,
            # we need to pass in a falsey string @FIXME once it has been fixed
            args.append(("in-pod", "''"))

    if podman_create_args:
        parsed_podman_create_args = _parse_args(
            _convert_args(podman_create_args), include_equal=True
        )
        # podman-create-args do not exist in podman-compose, but it uses podman-run-args
        # https://github.com/containers/podman-compose/blob/ae6be272b5b74799135e518bc106a0322dcf4771/podman_compose.py#L1341-L1342
        args.append(
            ("podman-run-args", "'{}'".format(" ".join(parsed_podman_create_args)))
        )
    if remove_orphans:
        cmd_args.append("remove-orphans")
    if force_recreate:
        cmd_args.append("force-recreate")
    if build:
        cmd_args.append("build")
    if build_args:
        cmd_args.extend(("build-arg", f"{k}={v}") for k, v in build_args.items())
    if pull:
        cmd_args.append("pull")

    _podman_compose(
        "up",
        args=args,
        cmd_args=cmd_args,
        runas=user,
        cwd=str(Path(composition).parent),
    )

    return install_units(
        project_name,
        pod_prefix=pod_prefix,
        container_prefix=container_prefix,
        separator=separator,
        user=user,
        ephemeral=ephemeral,
        restart_policy=restart_policy,
        restart_sec=restart_sec,
        service_overrides=service_overrides,
        pod_wants=pod_wants,
        stop_timeout=stop_timeout,
        enable_units=enable_units,
        now=now,
        remove_containers=ephemeral,
    )


def install_units(
    project,
    pod_prefix=None,
    container_prefix=None,
    separator=None,
    user=None,
    ephemeral=True,
    restart_policy=None,
    restart_sec=None,
    stop_timeout=None,
    service_overrides=None,
    pod_wants=True,
    generate_only=False,
    enable_units=True,
    now=False,
    remove_containers=False,
):
    """
    Install systemd units for a composition.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.install_units gitea user=gitea

    project
        Either the absolute path to a composition file or a project name.

    pod_prefix
        Unit name prefix for pods.
        Defaults to empty (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.

    ephemeral
        Create new containers on service start. Defaults to True.

    restart_policy
        Unit restart policy, defaults to ``on-failure``.
        This is not taken from the compose definition @TODO

    restart_sec
        Specify systemd RestartSec. Requires at least podman v4.3.

    stop_timeout
        Unit stop timeout, defaults to 10 [s].

    service_overrides
        Override generation parameters per unit. This should be a dictionary,
        mapping the service name as specified in the compose file
        to extra parameters (dict as well).

    pod_wants
        Ensure the pod dependencies for containers are enforced with ``Wants=``
        instead of ``Requires=``. This fixes issues when restarting a single
        container that is part of a pod, e.g. when auto-update is run.
        See https://github.com/containers/podman/issues/14546.

    generate_only
        Do not install the files, just return the contents.

    enable_units
        Enable the service units after installation. Defaults to True.

    now
        Start the services after installation. Defaults to False.

    remove_containers
        Ensure the template containers are removed after generating
        the service definitions. This is used to workaround an issue
        regarding ephemeral containers with dependencies. Defaults to false.
    """

    user = user or _try_find_user(project)
    project = _project_to_project_name(project)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix
    service_overrides = service_overrides or {}

    pod = pps(project, user=user)

    # pods managed by systemd need an infra container
    if pod and pod[0]["InfraId"]:
        ids = [pod[0]["Id"][:12]]
    else:
        ids = ps(project, user=user)

    if not ids:
        raise SaltInvocationError(
            f"Could not find existing pod or containers belonging to project {project}. "
            "Make sure to create them first."
        )

    cmd_args = [
        "name",
        "no-header",
    ]

    # if those are empty, the file name would still begin with a separator
    if container_prefix or pod_prefix:
        if separator is not None:
            cmd_args.append(("separator", separator))
    else:
        cmd_args.append(("separator", "''"))

    cmd_args.append(
        ("container-prefix", container_prefix if container_prefix else "''")
    )
    cmd_args.append(("pod-prefix", pod_prefix if pod_prefix else "''"))

    if ephemeral:
        cmd_args.append("new")
    if restart_policy is not None:
        cmd_args.append(("restart-policy", restart_policy))
    if restart_sec is not None:
        if __salt__["pkg_resource.version_compare"](podman_version(user), "<", "4.3"):
            log.info(
                "Skipping restart_sec since podman generate systemd does not support it below v4.3."
            )
        else:
            cmd_args.append(("restart-sec", restart_sec))
    if stop_timeout is not None:
        cmd_args.append(("time", stop_timeout))

    # need the definitions for finding the unit names
    definitions = {}
    for i in ids:
        extra_cmd_args = []
        if not isinstance(i, str):
            service_name = i["Labels"].get("com.docker.compose.service", "")
            if service_name in service_overrides:
                extra_cmd_args.extend(list(service_overrides[service_name].items()))
            i = i["Id"]

        out = _podman(
            "generate systemd",
            cmd_args=cmd_args + extra_cmd_args,
            params=[i],
            runas=user,
            json=True,
        )

        for name, unit in out["parsed"].items():
            if name in definitions:
                raise CommandExecutionError(
                    f"Your configuration resulted in duplicate unit names ({name})."
                )
            definitions[name] = unit

    if pod and pod_wants:
        pod_name = pod[0]["Name"]
        definitions[pod_name] = re.sub(
            r"^Requires=", "Wants=", definitions[pod_name], flags=re.MULTILINE
        )

    if generate_only:
        return definitions

    cwd = Path(service_dir(user))

    for service_name, service_definitions in definitions.items():
        ret = __salt__["file.manage_file"](
            cwd / (service_name + ".service"),
            contents=service_definitions,
            makedirs=True,
            user=user,
            group=__salt__["user.primary_group"](user),
            mode="0644",
            sfn=None,
            source=None,
            source_sum=None,
            attrs=None,
            saltenv=None,
            backup=False,
            ret=None,
        )
        if not ret["result"]:
            raise CommandExecutionError(ret["comment"])

    if remove_containers:
        if pod:
            ids = ps(project, user=user)
        cwd = ids[0]["Labels"]["com.docker.compose.project.working_dir"]
        _podman_compose(
            "down",
            runas=user,
            cwd=cwd,
        )
    # This assumes the name can be autodiscovered @FIXME
    # Previously, this was done with calling systemctl directly
    if enable_units:
        enable(
            project,
            project_name=project,
            pod_prefix=pod_prefix,
            container_prefix=container_prefix,
            separator=separator,
            user=user,
        )
    if now:
        start(
            project,
            project_name=project,
            pod_prefix=pod_prefix,
            container_prefix=container_prefix,
            separator=separator,
            user=user,
        )
    return True


@_needs_compose
def logs(
    composition,
    project_name=None,
    container=None,
    user=None,
):
    """
    Show logs of a composition.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.logs gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    container
        Only show logs of this container.

    user
        Run the command as this user. Defaults to the composition file parent dir owner
        (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)

    args = [("file", composition), ("project-name", project_name)]
    params = [container] if container else []

    return _podman_compose(
        "logs",
        args=args,
        runas=user,
        params=params,
        cwd=str(Path(composition).parent),
    )


def remove(
    composition,
    volumes=False,
    project_name=None,
    pod_prefix=None,
    container_prefix=None,
    separator=None,
    user=None,
):
    """
    Remove a container composition. Requires the service(s) to be dead.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.remove gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    volumes
        Also remove named volumes declared in the ``volumes`` section of the
        compose file and anonymous volumes attached to containers.
        Defaults to False.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    pod_prefix
        Unit name prefix for pods.
        Defaults to empty (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)

    if is_running(
        composition,
        project_name=project_name,
        pod_prefix=pod_prefix,
        container_prefix=container_prefix,
        separator=separator,
        user=user,
    ):
        raise CommandExecutionError(
            f"Cannot remove composition {composition} because the service(s) are still running."
        )

    # check if the unit files are ephemeral or not
    # a better check would be to run inspect_unit and look for AutoRemove @TODO
    containers = ps(
        composition,
        status=["created", "paused", "stopped", "exited", "unknown"],
        user=user,
    )

    containers += pps(composition, user=user)

    if containers or volumes:
        args = [("file", composition), ("project-name", project_name)]
        cmd_args = []
        if volumes:
            cmd_args.append("volumes")
        _podman_compose("down", args=args, cmd_args=cmd_args, runas=user)

    units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    for unit in list(units["containers"].values()) + list(units["pods"].values()):
        __salt__["file.remove"](unit)

    return True


def podman_compose_supports_pods(user=None):
    """
    Inquires whether podman-compose supports pod creation and whether
    it is forced. Versions 0.* require a pod, versions 1.* <= 1.0.3
    do not support it.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.podman_compose_supports_pods

    user
        Use the default podman-compose for this user. Defaults to
        Salt process user.
    """

    vers = version(user=user)

    # it seems versions 1.0.0 and 1.0.1 are not tagged
    unsupported = ["1.0.2", "1.0.3"]
    no_pod_switch = ["1.0.4"]
    pod_default_false = ["1.0.6"]

    ret = {"supported": True, "required": False}

    if vers.startswith("0."):
        ret["required"] = True
    elif vers.startswith("1.0") and vers in unsupported:
        ret["required"] = True
        ret["supported"] = False
    else:
        ret["no_pod_switch"] = vers in no_pod_switch
        ret["pod_default"] = vers not in pod_default_false

    return ret


def pps(
    project=None,
    status=None,
    name=None,
    pod_id=None,
    cnt_id=None,
    cnt_name=None,
    id_only=False,
    user=None,
):
    """
    List podman pods.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.pps gitea user=gitea

    project
        Filter pods running containers belonging to this project.
        Either the absolute path to a composition file or a project name.

    status
        Filter pods by status:
        ``created``, ``running``, ``paused``, ``stopped`` ``exited``, ``unknown``
        Can be a list, which will result in a union of the separate matches.

    name
        Filter pods by name. Matches a substring in a name.
        Can be a list, which will result in a union of the separate matches.

    pod_id
        Filter pods by ID.
        Can be a list, which will result in a union of the separate matches.

    cnt_id
        Filter pods by ID of containers inside.
        Can be a list, which will result in a union of the separate matches.

    cnt_name
        Filter pods by name of containers inside.
        Can be a list, which will result in a union of the separate matches.

    id_only
        Only return pod IDs instead of full information. Defaults to False.

    user
        List pods running under this user account.
        If ``project`` is defined and can be mapped to a compose file, defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    cmd_args = []

    if project is not None:
        # There is a --label filter for pod ps as well, but it
        # did not work in my testing (it should filter for pods
        # running matching containers)
        pod_id = pod_id or []
        pods = ps(project=project, pod_only=True, user=user)
        pod_id += list(set(pods))
        user = user or _try_find_user(project)

    def ensure_list(var):
        if not isinstance(var, list):
            var = [var]
        return var

    for var, fltr_name in [
        (status, "status"),
        (name, "name"),
        (pod_id, "id"),
        (cnt_id, "ctr-ids"),
        (cnt_name, "ctr-names"),
    ]:
        if var is not None:
            for fltr in ensure_list(var):
                cmd_args.append(("filter", f"{fltr_name}={fltr}"))

    if id_only:
        cmd_args.append(("format", "'{{.ID}}'"))

    out = _podman("pod ps", cmd_args=cmd_args, json=not id_only, runas=user)
    if id_only:
        return list(out["stdout"].splitlines())
    return out["parsed"]


def ps(
    project=None,
    status=None,
    name=None,
    cnt_id=None,
    exited=None,
    systemd_unit=None,
    id_only=False,
    pod_only=False,
    user=None,
    disable_user_automap=False,
):
    """
    List podman containers.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.ps gitea user=gitea

    project
        Filter containers belonging to this project.
        Either the absolute path to a composition file or a project name.

    status
        Filter containers by status:
        ``created``, ``running``, ``paused``, ``stopped`` ``exited``, ``unknown``
        Can be a list, which will result in a union of the separate matches.

    name
        Filter containers by name. Matches a substring in a name.
        Can be a list, which will result in a union of the separate matches.

    cnt_id
        Filter containers by ID.
        Can be a list, which will result in a union of the separate matches.

    exited
        Filter containers by exit signal.
        Can be a list, which will result in a union of the separate matches.

    systemd_unit
        Filter containers by value of PODMAN_SYSTEMD_UNIT.
        Can be a list, which will result in a union of the separate matches.

    id_only
        Only return container IDs instead of full information. Defaults to False.

    pod_only
        Only return the container pods instead of full information. Defaults to False.

    user
        List containers running under this user account.
        If ``project`` is defined and can be mapped to a compose file, defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.

    disable_user_automap
        Do not try to find the user when unspecified. Defaults to False.
        This is mainly needed to avoid a circular dependency.
    """

    cmd_args = ["all"]

    if project is not None:
        project = _project_to_project_name(project)
        cmd_args.append(("filter", f"label=io.podman.compose.project={project}"))
        if not disable_user_automap:
            user = user or _try_find_user(project)

    def ensure_list(var):
        if not isinstance(var, list):
            var = [var]
        return var

    if systemd_unit is not None:
        for val in ensure_list(systemd_unit):
            cmd_args.append(("filter", f"label=PODMAN_SYSTEMD_UNIT={val}"))

    for var, fltr_name in [
        (status, "status"),
        (name, "name"),
        (cnt_id, "id"),
        (exited, "exited"),
    ]:
        if var is not None:
            for fltr in ensure_list(var):
                cmd_args.append(("filter", f"{fltr_name}={fltr}"))

    if id_only:
        cmd_args.append(("format", "'{{.ID}}'"))
    elif pod_only:
        cmd_args.append(("format", "'{{.Pod}}'"))

    json = not (id_only or pod_only)

    out = _podman("ps", cmd_args=cmd_args, json=json, runas=user)
    if id_only or pod_only:
        return list(out["stdout"].splitlines())
    return out["parsed"]


def journal(
    composition,
    max_lines=10,
    project_name=None,
    container_prefix=None,
    pod_prefix=None,
    separator=None,
    user=None,
):
    """
    Show journalctl -u for the composition's service units.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.journal gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    max_lines
        Maximum log lines per service unit. Defaults to 10.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    pod_prefix
        Unit name prefix for pods. Defaults to empty
        (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """
    composition = find_compose_file(composition)
    user = user or _find_user(composition)
    units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )
    out = {}

    for unit in units["containers"]:
        journal_lines = _journalctl(unit, runas=user)["stdout"].splitlines()
        if len(journal_lines) > max_lines:
            journal_lines = journal_lines[:max_lines]
        out[unit] = "\n".join(journal_lines)

    return out


def status(
    composition,
    project_name=None,
    container_prefix=None,
    pod_prefix=None,
    separator=None,
    user=None,
):
    """
    Show systemctl status for the composition's service units.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.list_installed_units /opt/gitea/docker-compose.yml

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    pod_prefix
        Unit name prefix for pods. Defaults to empty
        (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    user = user or _find_user(composition)
    units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )
    out = {}

    for unit in units["containers"]:
        sctl_status = systemctl_status(unit, user)
        out[unit] = sctl_status

    return out


def disable(
    composition,
    project_name=None,
    pod_prefix=None,
    container_prefix=None,
    separator=None,
    user=None,
):
    """
    Disable the units for a composition from starting at boot.

    .. code-block:: bash

        salt '*' compose.disable gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    pod_prefix
        Unit name prefix for pods.
        Defaults to empty (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    if units["pods"]:
        disable_services = [next(iter(units["pods"]))]
    else:
        disable_services = list(units["containers"])

    if not disable_services:
        raise CommandExecutionError(
            f"Could not find any units belonging to project {project_name} for user {user}."
        )

    for service in disable_services:
        _check_for_unit_changes(service, user)
        systemctl_disable(service, user)

    return True


def enable(
    composition,
    project_name=None,
    pod_prefix=None,
    container_prefix=None,
    separator=None,
    user=None,
):
    """
    Enable the installed units for a composition to run at boot.

    .. code-block:: bash

        salt '*' compose.enable gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    pod_prefix
        Unit name prefix for pods.
        Defaults to empty (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    if units["pods"]:
        enable_services = [next(iter(units["pods"]))]
    else:
        enable_services = list(units["containers"])

    if not enable_services:
        raise CommandExecutionError(
            f"Could not find any units belonging to project {project_name} for user {user}."
        )

    for service in enable_services:
        _check_for_unit_changes(service, user)
        systemctl_enable(service, user)

    return True


def restart(
    composition,
    project_name=None,
    pod_prefix=None,
    container_prefix=None,
    separator=None,
    user=None,
):
    """
    Restart the installed units for a composition.

    .. code-block:: bash

        salt '*' compose.restart gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    pod_prefix
        Unit name prefix for pods.
        Defaults to empty (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    if units["pods"]:
        restart_services = [next(iter(units["pods"]))]
        # systemctl restart seems to fail for pods
        systemctl_stop(restart_services[0], user)
        func = systemctl_start
    else:
        restart_services = list(units["containers"])
        func = systemctl_restart

    if not restart_services:
        raise CommandExecutionError(
            f"Could not find any units belonging to project {project_name} for user {user}."
        )

    for service in restart_services:
        _check_for_unit_changes(service, user)
        func(service, user)

    return True


def start(
    composition,
    project_name=None,
    pod_prefix=None,
    container_prefix=None,
    separator=None,
    user=None,
):
    """
    Run the installed units for a composition.

    .. code-block:: bash

        salt '*' compose.start gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    pod_prefix
        Unit name prefix for pods.
        Defaults to empty (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    if units["pods"]:
        start_services = [next(iter(units["pods"]))]
    else:
        start_services = list(units["containers"])

    if not start_services:
        raise CommandExecutionError(
            f"Could not find any units belonging to project {project_name} for user {user}."
        )

    for service in start_services:
        _check_for_unit_changes(service, user)
        systemctl_start(service, user)

    return True


def stop(
    composition,
    project_name=None,
    pod_prefix=None,
    container_prefix=None,
    separator=None,
    user=None,
):
    """
    Stop the installed units for a composition.

    .. code-block:: bash

        salt '*' compose.stop gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    pod_prefix
        Unit name prefix for pods.
        Defaults to empty (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    if units["pods"]:
        stop_services = [next(iter(units["pods"]))]
    else:
        stop_services = list(units["containers"])

    if not stop_services:
        raise CommandExecutionError(
            f"Could not find any units belonging to project {project_name} for user {user}."
        )

    for service in stop_services:
        _check_for_unit_changes(service, user)
        systemctl_stop(service, user)

    return True


def is_disabled(
    composition,
    project_name=None,
    pod_prefix=None,
    container_prefix=None,
    separator=None,
    show_missing=False,
    user=None,
):
    """
    Check if the installed units for a composition are running.
    For boolean only, this is unnecessary, but show_missing provides
    some additional utility.

    .. code-block:: bash

        salt '*' compose.is_disabled gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    pod_prefix
        Unit name prefix for pods.
        Defaults to empty (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    show_missing
        Return list of enabled services that should be enabled for this
        call to succeed. Defaults to False.
        If enabled, the semantics change since an empty list of missing
        services is evaluated to False in Python.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    if units["pods"]:
        disabled_services = [next(iter(units["pods"]))]
    else:
        disabled_services = list(units["containers"])

    if not disabled_services:
        raise CommandExecutionError(
            f"Could not find any units belonging to project {project_name} for user {user}."
        )

    enabled = []

    for service in disabled_services:
        if systemctl_is_enabled(service, user):
            enabled.append(service)

    if show_missing:
        return enabled
    return not bool(enabled)


def is_enabled(
    composition,
    project_name=None,
    pod_prefix=None,
    container_prefix=None,
    separator=None,
    show_missing=False,
    user=None,
):
    """
    Check if the installed units for a composition are running.

    .. code-block:: bash

        salt '*' compose.is_enabled gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    pod_prefix
        Unit name prefix for pods.
        Defaults to empty (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    show_missing
        Return list of disabled services that should be enabled for this
        call to succeed. Defaults to False.
        If enabled, the semantics change since an empty list of missing
        services is evaluated to False in Python.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    if units["pods"]:
        enabled_services = [next(iter(units["pods"]))]
    else:
        enabled_services = list(units["containers"])

    if not enabled_services:
        raise CommandExecutionError(
            f"Could not find any units belonging to project {project_name} for user {user}."
        )

    disabled = []

    for service in enabled_services:
        if not systemctl_is_enabled(service, user):
            disabled.append(service)

    if show_missing:
        return disabled
    return not bool(disabled)


def is_running(
    composition,
    project_name=None,
    pod_prefix=None,
    container_prefix=None,
    separator=None,
    show_missing=False,
    user=None,
):
    """
    Check if the installed units for a composition are running.

    .. code-block:: bash

        salt '*' compose.is_running gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    pod_prefix
        Unit name prefix for pods.
        Defaults to empty (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    show_missing
        Return list of dead services that should be running for this
        call to succeed. Defaults to False.
        If enabled, the semantics change since an empty list of missing
        services is evaluated to False in Python.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    # need to check all the services, even with pods,
    # since their status does not rely on their containers (?)
    running_services = list(units["pods"]) + list(units["containers"])

    if not running_services:
        raise CommandExecutionError(
            f"Could not find any units belonging to project {project_name} for user {user}."
        )

    inactive = []

    for service in running_services:
        if not systemctl_is_running(service, user):
            inactive.append(service)

    if show_missing:
        return inactive
    return not bool(inactive)


def is_dead(
    composition,
    project_name=None,
    pod_prefix=None,
    container_prefix=None,
    separator=None,
    show_missing=False,
    user=None,
):
    """
    Check if the installed units for a composition are dead.
    For boolean only, this is unnecessary, but show_missing provides
    some additional utility.

    .. code-block:: bash

        salt '*' compose.is_dead gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    project_name
        The name of the project. Defaults to the name of the parent directory
        of the composition file.

    pod_prefix
        Unit name prefix for pods.
        Defaults to empty (podman-compose prefixes pod names with pod_ already).
        A different default can be set in ``compose.default_pod_prefix``.

    container_prefix:
        Unit name prefix for containers. Defaults to empty.
        A different default can be set in ``compose.default_container_prefix``.

    separator
        Unit name separator between prefix and name/id.
        Depending on the other prefixes, defaults to empty or dash.

    show_missing
        Return list of running services that should be dead for this
        call to succeed. Defaults to False.
        If enabled, the semantics change since an empty list of missing
        services is evaluated to False in Python.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """

    composition = find_compose_file(composition)
    project_name = project_name or _project_to_project_name(composition)
    user = user or _find_user(composition)
    container_prefix = container_prefix or default_container_prefix
    pod_prefix = pod_prefix or default_pod_prefix

    units = list_installed_units(
        composition,
        project_name=project_name,
        container_prefix=container_prefix,
        pod_prefix=pod_prefix,
        separator=separator,
        user=user,
    )

    # need to check all the services, even with pods,
    # since their status does not rely on their containers (?)
    dead_services = list(units["pods"]) + list(units["containers"])

    if not dead_services:
        raise CommandExecutionError(
            f"Could not find any units belonging to project {project_name} for user {user}."
        )

    active = []

    for service in dead_services:
        if systemctl_is_running(service, user):
            active.append(service)

    if show_missing:
        return active
    return not bool(active)


def version(user=None):
    """
    Get podman-compose version. Returns False if not installed (in $PATH)
    or not functional.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.version

    user
        Find podman-compose version for this user. Defaults to Salt process user.
    """

    out = _podman_compose("version", cmd_args=["short"], runas=user, raise_error=False)

    if out["retcode"]:
        return False
    return out["stdout"]


def podman_version(user=None):
    """
    Get podman version. Returns False if not installed (in $PATH)
    or not functional.

    CLI Example:

    .. code-block:: bash

        salt '*' compose.podman_version

    user
        Find podman version for this user. Defaults to Salt process user.
    """

    out = _podman("--version", runas=user, raise_error=False)
    if out["retcode"]:
        return False
    _version = re.findall(r"[0-9\.]+$", out["stdout"])[0]

    return _version


def autoupdate(
    composition,
    authfile=None,
    dry_run=False,
    user=None,
):
    """
    Run ``podman auto-update``. This automatically updates container images
    and containers that have the "io.containers.autoupdate=<policy>" label.

    .. code-block:: bash

        salt '*' compose.autoupdate gitea

    composition
        Some reference about where to find the project definitions.
        Can be an absolute path to the composition definitions (``docker-compose.yml``),
        the name of a project with available containers or the name
        of a directory in ``compose.containers_base``.

    authfile
        Path to the authentication file.

    dry_run
        Only check for pending updates.

    user
        The user account this composition has been applied to. Defaults to
        the composition file parent dir owner (depending on ``compose.default_to_dirowner``)
        or Salt process user. By default, defaults to the parent dir owner.
    """
    composition = find_compose_file(composition)
    user = user or _find_user(composition)

    cmd_args = []

    if authfile:
        cmd_args.append(("authfile", authfile))
    if dry_run:
        cmd_args.append("dry-run")

    return _podman("auto-update", cmd_args=cmd_args, runas=user)


def _project_to_project_name(project):
    """
    Returns the parent directory name of an absolute path to a composition file
    or the string itself. If it's a path, raises an error if it does not exist.
    """

    if project.startswith("/"):
        p = Path(project)
        if not p.exists():
            raise SaltInvocationError(f"Absolute path '{project}' does not exist.")
        return p.parent.name
    return project


def find_compose_file(project, user=None, raise_not_found_error=True):
    """
    Internal helper to find the project's composition file.

    Returns the absolute path to a compose file that belongs to this project.
    1. checks if the project is the path already
    2. tries to find existing containers from this project
    3. looks for ``<compose.containers_base>/<project>/docker-compose.yml``

    This was a hidden function, but is needed in the state module.
    Moving it to __utils__ would have been difficult since it relies
    on compose.ps (no salt dunder in utils).
    """
    if project.startswith("/"):
        p = Path(project)
        if not p.exists():
            if not raise_not_found_error:
                return False
            raise SaltInvocationError(f"Absolute path '{project}' does not exist.")
        return project

    containers = ps(project=project, user=user, disable_user_automap=True)

    if containers:
        files = {
            cnt["Labels"]["com.docker.compose.project.config_files"]
            for cnt in containers
            if "com.docker.compose.project.config_files" in cnt["Labels"]
        }

        if files:
            if len(files) > 1:
                raise CommandExecutionError(
                    f"Tried to autodiscover files for project {project}. "
                    "Found multiple, which is currently not supported by this module."
                )
            return files.pop()

    automapped = Path(containers_base) / project / "docker-compose.yml"
    if automapped.exists():
        return str(automapped)
    if not raise_not_found_error:
        return False

    raise SaltInvocationError(
        f"Could not find a composition file for project '{project}'."
    )


def _find_user(composition):
    """
    Resolves the owner of the parent directory of a compose file.
    Returns None for root, assumed to be the Salt process user.
    """

    if not default_to_dirowner:
        return None

    path = Path(composition)
    if path.exists():
        owner = path.parent.owner()
        if "root" == owner:
            # Salt process should run as root already, otherwise do not force
            return None
        return owner

    raise SaltInvocationError(f"Specified composition {composition} does not exist.")


def _try_find_user(project):
    """
    Tries to resolve the owner of the parent directory of a project.
    First searches for the compose file.
    Returns None (= Salt process user) if unsuccessful.
    """

    try:
        compose_file = find_compose_file(project)
    except SaltInvocationError:
        return None
    return _find_user(compose_file)
