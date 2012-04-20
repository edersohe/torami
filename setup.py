from setuptools import setup, find_packages
setup(
    name = "torami",
    version = "0.1",
    #packages = find_packages(),
    scripts = ['torami.py'],

    # Project uses reStructuredText, so ensure that the docutils get
    # installed or upgraded on the target machine
    install_requires = ['tornado>=2.2'],

    package_data = {
        # If any package contains *.txt or *.rst files, include them:
        '': ['*.txt', '*.rst'],
        # And include any *.msg files found in the 'hello' package, too:
        #'hello': ['*.msg'],
    },

    # metadata for upload to PyPI
    author = "Eder Sosa",
    author_email = "eder.sohe@gmail.com",
    description = "This is a short implementation of of Asterisk Manager Interface with Tornado framework",
    license = "MIT",
    keywords = "tornado asterisk manager ami",
    url = "http://github.com/edersohe/torami.git",   # project home page, if any

    # could also include long_description, download_url, classifiers, etc.
)