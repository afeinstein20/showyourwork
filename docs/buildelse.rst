Build someone else's article
----------------------------

If you would like to build an article created by someone else with |showyourwork|,
simply clone the article's GitHub repository:

.. code-block:: bash

    git clone https://github.com/user/repo
    cd repo

and, assuming you've installed |showyourwork|, run the following command in
the top level of the repository:

.. code-block:: bash

    showyourwork

.. raw:: html

    <pre>
    <span style="color:green;">Setting up the workflow...</span>
    <span style="color:green;">Generating the article PDF...</span>
    <span style="color:green;">Done!</span>
    </pre>

This will create a new conda environment for the workflow, install all the
required dependencies, and run all of the scripts needed to generate the figures
and results in the paper. At the end of the build, the article PDF will appear
in the top level of the repository (usually called ``ms.pdf``).

That's it for this quickstart tutorial. Please check out the rest of the
documentation for more information on how to customize your workflow,
debug issues, etc.
