import os
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from . import exceptions, logging, paths
from .subproc import get_stdout

OVERLEAF_BLANK_PROJECT_REGEX_TEMPLATE = r"[\n\r\s]+".join(
    [
        r"\\documentclass{article}",
        r"\\usepackage\[utf8\]{inputenc}",
        r"\\title{[^\n{}]+?}",
        r"\\author{[^\n{}]+?}",
        r"\\date{[^\n{}]+?}",
        r"\\begin{document}",
        r"\\maketitle",
        r"\\section{Introduction}",
        r"\\end{document}",
    ]
)

OVERLEAF_BLANK_PROJECT = r"""\documentclass{article}
\usepackage[utf8]{inputenc}

\title{blank project}
\author{Rodrigo Luger}
\date{April 2022}

\begin{document}

\maketitle

\section{Introduction}

\end{document}"""


def check_for_rate_limit(code, stdout, stderr):
    """
    Callback function to check if we hit a rate limit on Overleaf.

    """
    if stdout:
        logger = logging.get_logger()
        logger.debug(stdout)
    if code != 0:
        if "Rate limit exceeded" in stderr:
            raise exceptions.OverleafRateLimitExceeded()
        else:
            raise exceptions.CalledProcessError(stdout + "\n" + stderr)


def get_overleaf_credentials(
    overleaf_email="OVERLEAF_EMAIL",
    overleaf_password="OVERLEAF_PASSWORD",
    error_if_missing=False,
):
    """
    Return the user's Overleaf email and password, stored in env vars.

    Args:
        overleaf_email (str, optional): Environment variable containing the
            Overleaf account email address. Default ``OVERLEAF_EMAIL``.
        overleaf_password (str, optional): Environment variable containing the
            Overleaf account password. Default ``OVERLEAF_PASSWORD``.
        error_if_missing (bool, optional): Default ``False``.

    """
    creds = []
    for key in [overleaf_email, overleaf_password]:
        val = os.getenv(key, None)
        if val is None or not len(val):
            if error_if_missing:
                level = "error"
            else:
                # This exception is caught in the enclosing scope
                level = "warn"
            raise exceptions.MissingOverleafCredentials(level=level)
        else:
            # Replace special characters in the credentials
            val = quote(val, safe="")
            creds.append(val)

    return creds


def clone(project_id, path=None):
    """
    Clones an Overleaf remote locally.

    Args:
        project_id (str): The Overleaf project ID.
        path (str, optional): The path to the top level of the user's repo
            (if running from a different directory).

    Note that we don't qactually clone the repository (despite the name of this
    function) to avoid storing the url containing the Overleaf password in
    ``.git/config``. Instead, we initialize a new repository and pull from the
    remote.

    """
    # Logging
    logger = logging.get_logger()
    logger.info("Fetching Overleaf repo...")

    # Set up a fresh temp directory
    if paths.user(path=path).overleaf.exists():
        shutil.rmtree(paths.user(path=path).overleaf)
    paths.user(path=path).overleaf.mkdir(exist_ok=True)

    # Get the credentials & repo url
    overleaf_email, overleaf_password = get_overleaf_credentials()
    url = f"https://{overleaf_email}:{overleaf_password}@git.overleaf.com/{project_id}"

    # Set up a local version of the repo. We don't actually _clone_ it to avoid
    # storing the url containing the password in .git/config
    get_stdout(["git", "init"], cwd=str(paths.user(path=path).overleaf))

    # Overleaf uses a branch called 'master' by default. If the local config
    # uses a different name, we need to change it.
    get_stdout(
        ["git", "checkout", "-b", "master"],
        cwd=str(paths.user(path=path).overleaf),
    )

    # Pull from the repo (hide secrets)
    def callback(code, stdout, stderr):
        if stdout:
            logger.debug(stdout)
        if code != 0:
            if "Rate limit exceeded" in stderr:
                raise exceptions.OverleafRateLimitExceeded()
            elif "Authentication failed" in stderr:
                raise exceptions.OverleafAuthenticationError()
            else:
                raise exceptions.CalledProcessError(stdout + "\n" + stderr)

    get_stdout(
        ["git", "pull", url],
        cwd=str(paths.user(path=path).overleaf),
        secrets=[overleaf_email, overleaf_password],
        callback=callback,
    )


def wipe_remote(project_id):
    """
    Remove all files from the Overleaf project and start fresh as if it were a
    blank project.

    Args:
        project_id (str): The Overleaf project ID.

    """
    with TemporaryDirectory() as cwd:
        get_stdout(["git", "init"], cwd=cwd)
        get_stdout(["git", "checkout", "-b", "master"], cwd=cwd)
        (
            overleaf_email,
            overleaf_password,
        ) = get_overleaf_credentials()
        url = (
            f"https://{overleaf_email}:{overleaf_password}"
            f"@git.overleaf.com/{project_id}"
        )
        get_stdout(
            ["git", "pull", url],
            cwd=cwd,
            secrets=[overleaf_email, overleaf_password],
        )
        get_stdout(["git", "rm", "-r", "*"], cwd=cwd)
        with open(Path(cwd) / "main.tex", "w") as f:
            print(OVERLEAF_BLANK_PROJECT, file=f)
        get_stdout(["git", "add", "main.tex"], cwd=cwd)

        def callback(code, stdout, stderr):
            if code != 0:
                if (
                    "Your branch is up to date" in stdout + stderr
                    or "nothing to commit" in stdout + stderr
                    or "nothing added to commit" in stdout + stderr
                ):
                    pass
                else:
                    raise exceptions.CalledProcessError(stdout + "\n" + stderr)
            else:
                get_stdout(
                    ["git", "push", url, "master"],
                    cwd=cwd,
                    secrets=[overleaf_email, overleaf_password],
                    callback=check_for_rate_limit,
                )

        get_stdout(
            [
                "git",
                "-c",
                "user.name='showyourwork'",
                "-c",
                "user.email='showyourwork'",
                "commit",
                "-am",
                "automatic showyourwork update",
            ],
            cwd=cwd,
            callback=callback,
        )


def setup_remote(project_id, path=None):
    """
    Set up the bridge between the git repo and the Overleaf project for an
    empty Overleaf project with a given ID.

    Args:
        project_id (str): The Overleaf project ID.
        path (str, optional): The path to the top level of the user's repo
            (if running from a different directory).

    """
    # Setup logging
    logger = logging.get_logger()

    # Clone the repo
    clone(project_id, path=path)

    # Ensure this is in fact a *completely new* overleaf project
    files = list(paths.user(path=path).overleaf.glob("*"))
    files = [file for file in files if file.name != ".git"]
    try:
        if len(files) > 1:
            # User likely added a file
            raise Exception()
        elif len(files) == 1:
            # There's one file; ensure it's the default manuscript
            # by comparing it to the blank project regex template
            with open(files[0], "r") as f:
                contents = f.read()
            if re.match(OVERLEAF_BLANK_PROJECT_REGEX_TEMPLATE, contents):
                pass
            else:
                raise Exception()
    except Exception:
        raise exceptions.OverleafError(
            "Overleaf repository not empty! "
            "Refusing to rewrite files on remote."
        )
    else:
        # Delete the file
        files[0].unlink()
        get_stdout(
            ["git", "add", files[0].name],
            cwd=str(paths.user(path=path).overleaf),
        )

    # Copy over all files in the `tex` directory
    for file in paths.user(path=path).tex.glob("*"):
        # Copy it to the local version of the repo
        file = Path(file).resolve()
        remote_file = paths.user(path=path).overleaf / file.relative_to(
            paths.user(path=path).tex
        )
        if file.is_dir():
            if remote_file.exists():
                shutil.rmtree(remote_file)
            shutil.copytree(file, remote_file)
        else:
            shutil.copy(file, remote_file)

        # git-add the file
        get_stdout(
            [
                "git",
                "add",
                remote_file.relative_to(paths.user(path=path).overleaf),
            ],
            cwd=str(paths.user(path=path).overleaf),
        )

    # Commit callback
    def callback(code, stdout, stderr):
        if stdout:
            logger.debug(stdout)
        if code != 0:
            raise exceptions.CalledProcessError(stdout + "\n" + stderr)

    # Commit!
    logger.info("Setting up Overleaf repo...")
    get_stdout(
        [
            "git",
            "-c",
            "user.name='showyourwork'",
            "-c",
            "user.email='showyourwork'",
            "commit",
            "-m",
            "[showyourwork] automatic showyourwork update",
        ],
        cwd=str(paths.user(path=path).overleaf),
        callback=callback,
    )

    # Push (again being careful about secrets)
    overleaf_email, overleaf_password = get_overleaf_credentials()
    url = f"https://{overleaf_email}:{overleaf_password}@git.overleaf.com/{project_id}"
    get_stdout(
        ["git", "push", url, "master"],
        cwd=str(paths.user(path=path).overleaf),
        secrets=[overleaf_email, overleaf_password],
        callback=check_for_rate_limit,
    )


def push_files(files, project_id, path=None):
    """
    Push files to the Overleaf remote.

    Args:
        files (list): A list of strings corresponding to the paths of the
            files to be pushed to the Overleaf remote. These files must
            be located in ``src/tex/``. Subdirectories will be preserved.
        project_id (str): The Overleaf project ID.
        path (str, optional): The path to the top level of the user's repo
            (if running from a different directory).

    """
    # Disable if user didn't specify an id or if there are no files
    if not project_id or not files:
        return

    # Setup logging
    logger = logging.get_logger()

    # Clone the repo
    try:
        clone(project_id, path=path)
    except (
        exceptions.MissingOverleafCredentials,
        exceptions.OverleafAuthenticationError,
    ):
        # Not fatal!
        exceptions.restore_trace()
        return

    # Process each file
    skip = []
    for file in files:
        # Copy it to the local version of the repo
        if not Path(file).exists():
            skip.append(file)
            continue
        file = Path(file).resolve()
        remote_file = paths.user(path=path).overleaf / file.relative_to(
            paths.user(path=path).tex
        )
        if file.is_dir():
            if remote_file.exists():
                shutil.rmtree(remote_file)
            shutil.copytree(file, remote_file)
        else:
            shutil.copy(file, remote_file)

        # git-add the file
        get_stdout(
            [
                "git",
                "add",
                "-f",
                remote_file.relative_to(paths.user(path=path).overleaf),
            ],
            cwd=str(paths.user(path=path).overleaf),
        )

    # Remove missing files from the list
    if skip:
        skip_list = " ".join([str(s) for s in skip])
        logger.warning(f"Skipping missing file(s): {skip_list}")
        files = list(set(files) - set(skip))

    # Commit callback
    def callback(code, stdout, stderr):
        if stdout:
            logger.debug(stdout)
        file_list = " ".join([str(s) for s in files])
        if code != 0:
            if (
                "Your branch is up to date" in stdout + stderr
                or "nothing to commit" in stdout + stderr
                or "nothing added to commit" in stdout + stderr
            ):
                logger.warning(
                    f"No changes to commit to Overleaf: {file_list}"
                )
            else:
                raise exceptions.CalledProcessError(stdout + "\n" + stderr)
        else:
            logger.info(f"Pushing changes to Overleaf: {file_list}")

    # Commit!
    get_stdout(
        [
            "git",
            "-c",
            "user.name='showyourwork'",
            "-c",
            "user.email='showyourwork'",
            "commit",
            "-m",
            "[showyourwork] automatic showyourwork update",
        ],
        cwd=str(paths.user(path=path).overleaf),
        callback=callback,
    )

    # Push (again being careful about secrets)
    overleaf_email, overleaf_password = get_overleaf_credentials()
    url = f"https://{overleaf_email}:{overleaf_password}@git.overleaf.com/{project_id}"
    get_stdout(
        ["git", "push", url, "master"],
        cwd=str(paths.user(path=path).overleaf),
        secrets=[overleaf_email, overleaf_password],
        callback=check_for_rate_limit,
    )


def pull_files(
    files,
    project_id,
    error_if_missing=False,
    error_if_local_changes=False,
    path=None,
    commit_changes=True,
    push_changes=False,
):
    """
    Pull files from the Overleaf remote.

    Args:
        files (list): A list of strings corresponding to the paths of the
            files to be pulled from the Overleaf remote. These paths must
            be given relative to ``src/tex/`` or within subdirectories.
        project_id (str): The Overleaf project ID.
        error_if_missing (bool, optional): Default ``False``, which
            prints a warning but does not interrupt the workflow.
        error_if_local_changes (bool, optional): Default ``False``, which
            prints a warning but does not interrupt the workflow.
        path (str, optional): The path to the top level of the user's repo
            (if running from a different directory).
        commit_changes (bool, optional): Commit changes to the article
            repository? Default ``True``.
        push_changes (bool, optional): Push committed changes to the remote article
            repository? Only applicable if ``commit_changes`` is ``True``.
            Default ``False``.

    """
    # Disable if user didn't specify an id or if there are no files
    if not project_id or not files:
        return

    # Setup logging
    logger = logging.get_logger()

    # Clone the repo
    try:
        clone(project_id, path=path)
    except (
        exceptions.MissingOverleafCredentials,
        exceptions.OverleafAuthenticationError,
    ):
        # Not fatal!
        exceptions.restore_trace()
        return

    # Copy over the files
    file_list = " ".join([str(file) for file in files])
    logger.info(f"Pulling changes from Overleaf: {file_list}")
    for file in files:
        file = Path(file).absolute()
        remote_file = (
            paths.user(path=path).overleaf
            / file.relative_to(paths.user(path=path).tex)
        ).resolve()
        if not remote_file.exists():
            msg = (
                "File not found on Overleaf: "
                f"{remote_file.relative_to(paths.user(path=path).overleaf)}"
            )
            if error_if_missing:
                raise exceptions.OverleafError(msg)
            else:
                logger.error(msg)
                continue

        # Ensure there are no uncommitted changes to the local file/directory
        try:
            get_stdout(
                f'git diff --quiet -- "{file}"',
                shell=True,
                cwd=paths.user(path=path).repo,
            )
        except Exception:
            msg = (
                "Uncommitted changes to local file: "
                f"{remote_file.relative_to(paths.user(path=path).overleaf)}. "
                "Refusing to overwrite with Overleaf version."
            )
            if error_if_local_changes:
                raise exceptions.OverleafError(msg)
            else:
                logger.error(msg)
                continue

        # Ensure the last change was an automatic showyourwork commit
        # based on inspection of the commit message
        # (must contain `[showyourwork]` or must not be tracked by git)
        def callback(code, stdout, stderr):
            assert (
                len(stdout.lower()) == 0 or "[showyourwork]" in stdout.lower()
            )

        try:
            get_stdout(
                f'git log -n 1 --pretty=format:%s -- "{file}"',
                shell=True,
                cwd=paths.user(path=path).repo,
                callback=callback,
            )
        except Exception:
            msg = (
                "Local file changed since the last Overleaf sync: "
                f"{remote_file.relative_to(paths.user(path=path).overleaf)}. "
                "Refusing to overwrite with Overleaf version. Please see the "
                "docs for details on how to resolve this."
            )
            if error_if_local_changes:
                raise exceptions.OverleafError(msg)
            else:
                logger.error(msg)
                continue

        # Finally, overwrite the file/folder with the version on Overleaf
        if remote_file.is_dir():
            if file.exists():
                shutil.rmtree(file)
            shutil.copytree(remote_file, file)
        else:
            # Only copy if the files actually differ
            def callback(code, stdout, stderr):
                if code != 0:
                    shutil.copy(remote_file, file)
                    get_stdout(
                        [
                            "git",
                            "add",
                            "-f",
                            file.relative_to(paths.user(path=path).repo),
                        ],
                        cwd=paths.user(path=path).repo,
                    )

            get_stdout(["diff", remote_file, file], callback=callback)

    if commit_changes:

        def callback(code, stdout, stderr):
            if code == 0:
                logger.info(
                    "Overleaf changes committed to the repo. Don't forget to push!"
                )
            else:
                if (
                    "Your branch is up to date" in stdout + stderr
                    or "nothing to commit" in stdout + stderr
                    or "nothing added to commit" in stdout + stderr
                ):
                    logger.warning(
                        f"No Overleaf changes to commit to the repo."
                    )
                else:
                    raise exceptions.CalledProcessError(stdout + "\n" + stderr)

        get_stdout(
            [
                "git",
                "-c",
                "user.name='showyourwork'",
                "-c",
                "user.email='showyourwork'",
                "commit",
                "-m",
                "[showyourwork] overleaf sync",
            ],
            cwd=paths.user(path=path).repo,
            callback=callback,
        )

        if push_changes:
            get_stdout(["git", "push"], cwd=paths.user(path=path).repo)
