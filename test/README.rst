Tests
=====

A
`docker-mailserver <https://github.com/docker-mailserver/docker-mailserver>`__
image is created at ``/tmp/mailserver``.

To reset the test setup:

.. code:: sh

    cd /tmp/mailserver
    docker-compose down
    sudo rm -rf /tmp/mailserver/

The ``sudo`` is needed for the self-signed ``.pem`` files,
created by ``self_sign.sh``.

``prepare_test.sh 2/3`` sets up ``/tmp/mailserver`` for Python 2 or Python 3.

The tests are in ``.bats`` files.

``make test2`` runs tests for Python 2.
``/tmp/mailserver`` is not renewed on repeated runs.

``make test3`` runs tests for Python 3.
``/tmp/mailserver`` is not renewed on repeated runs.

``make test`` runs tests for Python 2 and Python 3.
``/tmp/mailserver`` is renewed on repeated runs.

To force a renew in the next make run.

.. code:: sh

    rm -rf /tmp/mailserver/python?

