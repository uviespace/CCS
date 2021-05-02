How to use it
=============
The path to the default configuration file will be set generically during the installation.

Installation
------------
Open the terminal. Change to the 'implementation' folder or your project. There is a Makefile which has a goal named 'install-confignator'.

.. code:: bash

    make install-confignator

This will install the confignator package with pip3 and thus can be imported as Python module without further action.
The path to the default configuration file will be set during the installation.

Usage
-----
There are top-level package functions which can be used without loading a configuration before.
All these can get passed a logger. If no logger is passed, the module logger will be used.

    * :func:`confignator.get_config <confignator.config.get_config>`
    * :func:`confignator.get_option <confignator.config.get_option>`
    * :func:`confignator.get_bool_option <confignator.config.get_bool_option>`
    * :func:`confignator.save_option <confignator.config.save_option>`

There are confignator instance functions, which can be used after loading a configuration:

    * :func:`confignator.config.Config.save_to_file <confignator.config.Config.save_to_file>`


Currently these use cases are considered:

    * read only: retrieve a option from any configfile in a one-liner (for example to get a path)

        * cfg = confignator.get_config() -> loads big-merger-config
        * opt = confignator.get_option() -> gives the value of the option after loading the big-merger-config

            * file crossing interpolation of option values
            * always loads the files
            * no need to specify the file where the option is located

        * opt = confignator.get_bool_option() -> same as get_option, but the option is parsed as boolean (False, false, 0 => False)

    * manipulate the configuration, use it and save it (e.g.: a application loads it's own configuration file)

        * cfg = confignator.get_config(file_path=<filepath>) -> loads only the specified configuration file

            * instance cfg: no reloading after changing a section/option
            * cfg.save_to_file(): saves the configuration as file
            * cfg: all methods and attributes of the super class configparser.Parser are available

    * changing and save a existing option, without loading a specified configuration file prior

        * confignator.save_option()

            * -> loads the big-merger-config
            * -> looks, in which file the option occurs (the [section][option] needs to be unique)
            * -> only if one occurrence, this file is loaded in single mode, the option set and this config saved

**Get a configuration or a option of a configuration:**

For retrieving a option, the function *get_option* can be used, without loading a configuration prior. This function will return a string.

.. code:: python

    import confignator
    # get the default configuration
    cfg = confignator.get_config()
    cfg = confignator.get_config(logger=logger)

    # get the configuration of a specified file
    cfg = confignator.get_config(file_path='file_path', logger=logger)

    # get the configuration of a specified file, do not load denoted configuration files (the files listed in section *[config-files]*)
    cfg = confignator.get_config(file_path='file_path', load_denoted_files=False, logger=logger)

    # get the configuration of a specified file, do not load the denoted files nor the basic configuration files (confignator.cfg, egse.cfg)
    cfg = confignator.get_config(file_path='file_path', load_denoted_files=False, load_basic_files=False, logger=logger)

    # get a option of the default configuration
    opt = confignator.get_option(section='section_name', option='option_name', logger=logger)


**Using the GUI**

There is a GUI available for editing the configuration files. If called without argument, the default configuration will be loaded. This is a merge out ouf of configuration files. If a file_path is provided only this single file will be opened.

.. code:: python

    import confignator
    # starts the configuration editor GUI and loads the default configuration
    confignator.editor()
    # starts the configuration editor GUI and loads a specified file
    confignator.editor(file_path='file_path')

**Changing and saving of a option**

There is the top-level function *save_option*. This can be used to set a option and save this change. If not file_path is provided the default configuration and all automatically loaded configurations will be searched for the section and option. Only if the section and option are unique, the option will be saved. It is saved in the file where it was found.
If a file_path was provided, only this file will be searched for this section and option.

.. code:: python

    import confignator
    confignator.save_option(section='section', option='option', value='value', logger=logger)


**Saving a configuration as file**

This will save the configuration of all the loaded and merged config files into one file. To save a merge the file_path argument needs to be provided.
In order to change and save a single configuration file, it needs to be loaded as single file. If the loaded configuration is a single file, no file_path has to be provided. It is saved in this file. For saving it to another file, provide a file_path.

.. code:: python

    import confignator
    cfg = confignator.get_config()
    cfg.save_to_file()
    # in order to save it to another file ('save_as')
    cfg.save_to_file(file_path=<file_path>)


Configuration file syntax
-------------------------
It is used a INI file structure. Enhanced interpolation with ${<section>:<option} is enabled.
For more information check out Configparser-Documentation_

.. _Configparser-Documentation: https://docs.python.org/3/library/configparser.html

The confignator uses the default behaviour of the Configparser:

    * section names are case sensitive
    * keys are not case sensitive and are stored in lower case


Configuration file hierarchy
----------------------------
There is one top level config file, also called the default config file (**egse.cfg**).
It's location is the 'implementation' folder of the project.
Within this configuration file a Section 'config-files' holds the paths to all other config files, which should be loaded.
Using the function confignator.get_config will load all configuration files listed in the **'config-files' Section**.


Example of the top level egse.cfg:
----------------------------------

.. code:: ini

    [paths]
    obsw = /home/user/smile/implementation
    tst = ${obsw}/Tst
    ifsw = /home/user/cheops
    ccs = ${obsw}/Ccs/devel
    obc = ${obsw}/CrObc/build/pc
    ia = ${obsw}/CrIa/build/pc
    sem = ${ifsw}/CrSem/build/pc/
    datasim = ${ifsw}/SemDataSim/FGS_Data_Simulator

    [dbus_names]
    editor = com.editor.communication1
    poolviewer = com.poolviewer.communication1
    poolmanager = com.poolmanager.communication1
    monitor = com.monitor.communication1

    [config-files]
    tst = ${paths:tst}/tst/tst.cfg


How can I change the *generated* path of the default configuration file?
------------------------------------------------------------------------
This path is written to the file 'confignator.cfg' when executing the goal 'build' of the Makefile. This file can be
found in the installation directory of the confignator package (python -> site_packages).
IMPORTANT: the directory, where the Makefile goal is called, will be set as the path to the default configuration file

**Changing the default configuration file path can be achieved by changing the Makefile.**

Troubleshooting
---------------
If something does not work when using the confignator you may find more information in the log files.
There is a log file for the configuration editor. The path to this file is set in the BasicConfiguration.

If you are using a own logger, which you pass for example to the function *get_option*, check the log file of your logger.
The confignator uses for the most logging messages the level logging.DEBUG.

Using the confignator functions without user specified logger, will result that the confignator will log into a file in its installation folder.

All log messages with a level higher than logging.WARNING will be written to the console StreamHandler.