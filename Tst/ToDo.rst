TST:

    * Run tests as parallel processes

        * stop/abort step or test
        * execute two or more twigs parallel

    * appearance

        * overview of steps in a test

    * execution of steps

        * use the text editor of the CCS editor
        * execution sends code to a console

    * TC recognition feature

    * verification code functionality

    * lock the numbering feature

TST - search feature:

    * putting all tests and code snippets into a database

        * add test from folder
        * add favorites (this are code blocks meant to be a template)

    * create search engine for this database

        * assumption: database contains about 200 tests, with favorites
        * combination of text and filter values -> combination logic

    * UI for the search

        * input field

            * start searching while typing or
            * start searching when clicking on button

        * predefined filter (TC, only in command block, only in verification, ...)
        * display of the search results

            * compact list on the left

                * show the line of occurrence

            * detail view of full step on the right
            * features

                * click on list entry to show it in detail window
                * ctrl + c or drag and drop

                    * on step: copy whole step (command and verification blocks)
                    * on command or verification block: copy this block
                    * on text: copy marked text


meeting with Roland 13.Feb2020

    * lock-mechanism for tests

        * locking fixes the number of the steps, new steps are substeps (e.g.: 3.1, 3.2, ...)
        * button for manually renumber all steps after unlocking
        * steps can be moved per drag and drop

    * code reuse feature:

        * all test are in a tree in order to browse them. Steps and code can be shown by clickung on a +
        * section for favorites
        * to add a new code, it should be possible to do this per drag and drop
        * importing of folder and files to populate the DB

    * in order to connect the TST with other applications the common approach should be used

    * the step widget should have a little toolbar before the description

        * step is active - checkbox
        * execute step - button
        * delete step - button