Tests
=====

Requirements:
- pip install pytest

bats is part of docker-mailserver.

A
`docker-mailserver <https://github.com/docker-mailserver/docker-mailserver>`__
image is created at ``/tmp/mailserver``.

To reset the test setup:

.. code:: sh

    cd /tmp/mailserver
    docker-compose down
    cd ..
    sudo rm -rf /tmp/mailserver/

The ``sudo`` is needed for the self-signed ``.pem`` files,
created by ``self_sign.sh``.

The tests are in ``.bats`` files.

``make test`` runs all tests.
You might need to enter a python virtual environment first.

