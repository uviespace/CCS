.. TestSpecificationTool documentation master file, created by
   sphinx-quickstart on Fri Jul 13 11:20:18 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to TestSpecificationTool's documentation!
=================================================

Milestone *basic functionality* due September
---------------------------------------------
Goal is to create a very simple test case and the generation of the output products should be working.

    * verification ID information flow should work
    * only commands and verification should be generated as output products (the .tex file is not important)
    * StepWidget features

        * description
        * comment
        * code editors: commands, verification
        * manually enter verification ID

Very simple test case:

    * Description: changing the frequency of a housekeeping
    * consisting out of 2-3 steps
    * no loops over steps, no parallel thread

ToDo list:

    * finish StepWidget
    * sketch desk (GUI) <-> data model
    * data model <-> JSON file
    * data model -> output products (generator)
    * verification ID flow
    * command and verification log file parser

.. toctree::
   :caption: Content
   :name: mastertoc
   :numbered:
   :titlesonly:

   TST <_apidocfiles/tst>
   Testing Library <_apidocfiles/testlib>
   Progress View <_apidocfiles/progress_view>
   Configuration Editor <_apidocfiles/confignator>

.. automodule:: tst
    :members:
    :undoc-members:
    :show-inheritance:

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
