Building remotely
-----------------

Whenever you make a change to your article (add text, add a figure, edit
a script), make sure to ``git add`` any new/modified files,
commit your changes, and then push to the GitHub remote:

.. code-block:: bash

    git add src/scripts/random_numbers.py
    git add src/tex/ms.tex
    git commit -m "added a new figure"
    git push -u origin main


.. note::

    Note that we're only adding the figure *script*, not the figure file, to
    the list of files tracked by ``git``. In fact, if you try to add the figure
    file, you'll get an error:

    .. code-block:: bash

        git add src/tex/figures/random_numbers.pdf

        The following paths are ignored by one of your .gitignore files:
        src/tex/figures/random_numbers.pdf
        Use -f if you really want to add them.

.. |actions| image:: _static/actions_tab.png
    :width: 60
    :target: https://docs.github.com/en/actions

As soon as you push your changes to GitHub, a GitHub Action will be triggered
on your repository, which will build your article from scratch on the cloud.
To track the build, click on the |actions| tab of your repository. The first
time your article is built, the action will have to download and install
``conda``, so it will likely take a few minutes. Subsequent builds take
advantage of intelligent cross-build caching, so they will likely run
faster.

When the build is done, you can click on any of the badges on the front
page of your repository:

.. image:: _static/badges.png
   :width: 30%
   :align: center

.. raw:: html

    <br/>

these will take you to the build logs, the article tarball (containing the
TeX files and all generated figures), and the compiled PDF of the article,
respectively.
