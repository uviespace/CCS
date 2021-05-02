#!/usr/bin/env bash


# Deleting the old build
echo -e "Building the documentation for the TestSpecificationTool (TST)\n"

echo -e "\e[1m==================\e[0m"
echo -e "\e[1mDeleting old build\e[0m"
echo -e "\e[1m==================\e[0m"
rm -r ./doc/build
rm -r ./doc/source/_apidocfiles
mkdir ./doc/source/_static
echo ""


# Run sphinx apidoc
echo -e "\e[1m=====================\e[0m"
echo -e "\e[1mRunning sphinx apidoc\e[0m"
echo -e "\e[1m=====================\e[0m"
dest="doc/source/_apidocfiles/"

src_1="tst"
src_2="confignator/confignator"
src_3="testing_library/testlib"
src_4="progress_view"
srcs=($src_1 $src_2 $src_3 $src_4)

apidoc_succ=true
for src in "${srcs[@]}"; do
    sphinx-apidoc --separate -f -e -d 10 --implicit-namespaces -o $dest $src "*generator_templates"
    succ_1=$?
    if [ $succ_1 -eq 0 ]; then
        echo -e "\e[32mSuccessful ran command sphinx-apidoc on folder" $src "\e[0m"
    else
        apidoc_succ=false
        echo -e "\e[1m\e[31mFAILED\e[0m to run command sphinx-apidoc on folder" $src "\e[0m"
    fi
done
if $apidoc_succ; then
    echo -e "\e[1m\e[32m==============================\e[0m"
    echo -e "\e[1m\e[32mSuccessfully ran sphinx-apidoc\e[0m"
    echo -e "\e[1m\e[32m==============================\e[0m"
else
    echo -e "\e[1m\e[31m============================\e[0m"
    echo -e "\e[1m\e[31mFailed running sphinx apidoc\e[0m"
    echo -e "\e[1m\e[31m============================\e[0m"
fi
echo ""


# Building the HTML
echo -e "\e[1m========================\e[0m"
echo -e "\e[1mRunning sphinx make HTML\e[0m"
echo -e "\e[1m========================\e[0m"
pushd doc 
make html
succ_html=$?
popd
if [[ $succ_html -eq 0 ]]; then
    echo -e "\e[1m\e[32m=================================\e[0m"
    echo -e "\e[1m\e[32mSuccessfully ran sphinx make HTML\e[0m"
    echo -e "\e[1m\e[32m=================================\e[0m"
    echo ""
    echo -e "\e[1m====================================\e[0m"
    echo -e "\e[1mOpening the documentation in Firefox\e[0m"
    echo -e "\e[1m====================================\e[0m"
    firefox ./doc/build/html/index.html &
    if [[ $? -eq 0 ]]; then
         echo -e "\e[1m\e[32m================================================\e[0m"
         echo -e "\e[1m\e[32mSuccessfully opened the documentation in Firefox\e[0m"
         echo -e "\e[1m\e[32m================================================\e[0m"
    else
         echo -e "\e[1m\e[31m===========================================\e[0m"
         echo -e "\e[1m\e[31mFailed opening the documentation in Firefox\e[0m"
         echo -e "\e[1m\e[31m===========================================\e[0m"
    fi
else
    echo -e "\e[1m\e[31m===============================\e[0m"
    echo -e "\e[1m\e[31mFailed running sphinx make HTML\e[0m"
    echo -e "\e[1m\e[31m===============================\e[0m"
fi

