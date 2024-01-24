"""
Execution module specifically for managing user services, which is impossible
with the included modules. The first draft was extracted from my ``compose`` modules.
This is heavily based on the default modules. @TODO PR

A user session is required. Currently, this is achieved by requiring
having lingering enabled on the target user account.
Enabling lingering is only one method though, the other one using
machinectl / systemctl --user -M.

I forgot which problems I had using this method though.

https://github.com/saltstack/salt/issues/40887
"""

import logging
from pathlib import Path

import salt.utils.systemd
from salt.exceptions import CommandExecutionError, SaltInvocationError

log = logging.getLogger(__name__)
__virtualname__ = "user_service"

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


# This is taken 1:1 from the systemd_service module
def __virtual__():
    """
    Only work on systems that have been booted with systemd
    """
    is_linux = __grains__.get("kernel") == "Linux"
    is_booted = salt.utils.systemd.booted(__context__)
    is_offline = salt.utils.systemd.offline(__context__)
    if is_linux and (is_booted or is_offline):
        return __virtualname__
    return (
        False,
        "The systemd user execution module failed to load: only available on Linux "
        "systems which have been booted with systemd.",
    )


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

        salt '*' user_service.systemctl start params=[gitea.service] user=gitea

    command
        systemctl subcommand to execute

    args
        Command line options/flags for systemctl itself to pass.

    cmd_args
        Command line options/flags for the systemctl subcommand to pass.

    params
        Positional arguments to pass to the systemctl subcommand.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    return _systemctl(command, args=args, cmd_args=cmd_args, params=params, runas=user)


def status(name, user=None):
    """
    Returns the output of systemctl status (cmd.run_all).

    CLI Example:

    .. code-block:: bash

        salt '*' user_service.status podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """
    return _systemctl_status(name, user)


def is_enabled(unit, user=None):
    """
    Check whether a systemd unit is enabled. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' user_service.is_enabled podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    out = _systemctl("is-enabled", params=[unit], runas=user, expect_error=True)
    return "enabled" == out["stdout"]


def is_running(unit, user=None):
    """
    Check whether a systemd unit is running. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' user_service.is_running podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    out = _systemctl("is-active", params=[unit], runas=user, expect_error=True)
    return 0 == out["retcode"]


def start(unit, user=None):
    """
    Start a systemd unit. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' user_service.start podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    _systemctl("start", params=[unit], runas=user)
    return True


def stop(unit, user=None):
    """
    Stop a systemd unit. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' user_service.stop podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    _systemctl("stop", params=[unit], runas=user)
    return True


def restart(unit, user=None):
    """
    Restart a systemd unit. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' user_service.restart drone user=drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    _systemctl("restart", params=[unit], runas=user)
    return True


def reload(unit, user=None):
    """
    Reload a systemd unit. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' user_service.reload drone user=drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    _systemctl("reload", params=[unit], runas=user)
    return True


def enable(unit, user=None):
    """
    Enable a systemd unit. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' user_service.enable podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    _systemctl("enable", params=[unit], runas=user)
    return True


def disable(unit, user=None):
    """
    Disable a systemd unit. This is an extension to the
    official module, which allows executing this for a specific user.

    CLI Example:

    .. code-block:: bash

        salt '*' user_service.disable podman.sock drone

    unit
        Name of the systemd unit.

    user
        The user to run systemctl with. Defaults to
        Salt process user.
    """

    _systemctl("disable", params=[unit], runas=user)
    return True


def daemon_reload(user=None):
    """
    Reloads systemd unit files. This is an extension to the
    official module, which allows executing this for a specific
    user.

    CLI Example:

    .. code-block:: bash

        salt '*' user_service.reload gitea

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

        salt '*' user_service.lingering_disable user

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

        salt '*' user_service.lingering_enable user

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

        salt '*' user_service.lingering_enabled user

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


def journal(unit, max_lines=20, user=None):
    """
    Return the last journal log entries for a unit.

    CLI Example:

    .. code-block:: bash

        salt '*' user_service.journal jellyfin user=jellyfin

    unit
        The name of the unit to return entries for.

    max_lines
        The maximum number of lines to return. Defaults to 20.

    user
        The user that runs the unit. Defautls to Salt process user.
    """
    journal_lines = _journalctl(unit, runas=user)["stdout"].splitlines()
    if len(journal_lines) > max_lines:
        journal_lines = journal_lines[:max_lines]
    return "\n".join(journal_lines)


def get_running(user=None):
    """
    Return a list of all running services, so far as systemd is concerned

    CLI Example:

    .. code-block:: bash

        salt '*' service.get_running user=jellyfin

    user
        The user to list the units for. Defautls to Salt process user.
    """
    ret = set()
    # Get running systemd units
    out = _systemctl("", args=["full", "no-legend", "no-pager"], runas=user)
    for line in out["stdout"].splitlines():
        try:
            comps = line.strip().split()
            fullname = comps[0]
            if len(comps) > 3:
                active_state = comps[3]
        except ValueError as exc:
            log.error(exc)
            continue
        else:
            if active_state != "running":
                continue
        try:
            unit_name, unit_type = fullname.rsplit(".", maxsplit=1)
        except ValueError:
            continue
        if unit_type in VALID_UNIT_TYPES:
            ret.add(unit_name if unit_type == "service" else fullname)

    return sorted(ret)


def get_enabled(user=None):
    """
    Return a list of all enabled services

    CLI Example:

    .. code-block:: bash

        salt '*' service.get_enabled user=jellyfin

    user
        The user to list the units for. Defautls to Salt process user.
    """
    return _get_state(user, "enabled")


def get_disabled(user=None):
    """
    Return a list of all disabled services

    CLI Example:

    .. code-block:: bash

        salt '*' service.get_disabled user=jellyfin

    user
        The user to list the units for. Defautls to Salt process user.
    """
    return _get_state(user, "disabled")


def get_static(user=None):
    """
    Return a list of all static services

    CLI Example:

    .. code-block:: bash

        salt '*' service.get_static user=jellyfin

    user
        The user to list the units for. Defautls to Salt process user.
    """
    return _get_state(user, "static")


def show(name, user=None):
    """
    Show properties of one or more units/jobs or the manager

    user
        The user to show the unit for. Defautls to Salt process user.

    CLI Example:

    .. code-block:: bash

        salt '*' user_service.show pod_jellyfin user=jellyfin
    """
    ret = {}
    out = _systemctl("show", params=[name], runas=user)
    for line in out["stdout"].splitlines():
        comps = line.split("=")
        name = comps[0]
        value = "=".join(comps[1:])
        if value.startswith("{"):
            value = value.replace("{", "").replace("}", "")
            ret[name] = {}
            for item in value.split(" ; "):
                comps = item.split("=")
                ret[name][comps[0].strip()] = comps[1].strip()
        elif name in ("Before", "After", "Wants"):
            ret[name] = value.split()
        else:
            ret[name] = value

    return ret


def _get_state(user, state):
    ret = set()
    out = _systemctl(
        "list-unit-files", args=["full", "no-legend", "no-pager"], runas=user
    )
    for line in out["stdout"].splitlines():
        try:
            fullname, unit_state = line.strip().split()[:2]
        except ValueError:
            continue
        else:
            # Arch Linux adds a third column, which we want to ignore
            if unit_state.split()[0] != state:
                continue
        try:
            unit_name, unit_type = fullname.rsplit(".", 1)
        except ValueError:
            continue
        if unit_type in VALID_UNIT_TYPES:
            ret.add(unit_name if unit_type == "service" else fullname)
    return sorted(ret)


def _run(
    bin_path,
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
    Generic helper for running some console commands.

    bin_path
        Path to the binary to run.

    command
        Subcommand of the program to run (eg ``enable`` in ``systemctl enable``).

    args
        Arguments (options/flags) to the base program.

    cmd_args
        Arguments (options/flags) to the subcommand.

    params
        Positional parameters to pass (after ``--`` – e.g. ``git checkout HEAD -- sample.py)

    runas
        Run as a different user account.

    cwd
        Run in a specific working directory.

    raise_error
        Raise exceptions when the exit code is nonzero. Defaults to true.

    expect_error
        Do not log nonzero exit codes as errors. Defaults to false.
        (``ignore_retcode`` in ``cmd.run``).
    """

    args = args or []
    cmd_args = cmd_args or []

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

    return out


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
    Helper for running arbitary ``systemctl`` commands related to user services.
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
    Helper for running arbitary ``journalctl`` commands related to podman services.
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


def service_dir(user=None):
    """
    Returns the path of the directory service units should be
    installed in.


    CLI Example:

    .. code-block:: bash

        salt '*' user_service.service_dir gitea

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

    contextkey = f"user_service._check_for_unit_changes.{name}"
    if user is not None:
        contextkey += f".{user}"

    if contextkey not in __context__:
        if _untracked_custom_unit_found(name, user) or _unit_file_changed(name, user):
            reload()
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
            if key.startswith("user_service._systemctl_status."):
                __context__.pop(key)
        except AttributeError:
            continue


def _systemctl_status(name, user=None):
    """
    Helper function which leverages __context__ to keep from running 'systemctl
    status' more than once.
    This function is modified from the official systemd_service module.
    """

    contextkey = f"user_service._systemctl_status.{name}"
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
