# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

.PHONY: doc
doc:
	links -dump docs/documentation.html > docs/documentation.txt
	links -dump docs/configuration.html > docs/configuration.txt
	links -dump docs/faq.html > docs/faq.txt
	links -dump docs/troubleshooting.html > docs/troubleshooting.txt

.PHONY: cleantest
cleantest:
	rm -rf /tmp/mailserver/python?

.PHONY: test2
test2:
	cd test && ./prepare_test.sh 2
	cd /tmp/mailserver && test/bats/bin/bats test/test_getmail_with_docker_mailserver.bats

.PHONY: test3
test3:
	cd test && ./prepare_test.sh 3
	cd /tmp/mailserver && test/bats/bin/bats test/test_getmail_with_docker_mailserver.bats

.PHONY: test
test: cleantest test3 test2

.PHONY: check
check:
	/usr/bin/man -l docs/getmail.1
	restview --long-description --strict

.PHONY: dist
dist: doc
	echo "need sudo to create wheel"
	sudo python setup.py bdist_wheel

.PHONY: up
up:
	twine upload dist/`ls dist -rt | tail -1`

.PHONY: tag
tag:
	$(eval TAGMSG="v$(shell ./getmail --version | cut -d ' ' -f 2)")
	echo $(TAGMSG)
	git tag -s $(TAGMSG) -m"$(TAGMSG)"
	git verify-tag $(TAGMSG)
	git push origin $(TAGMSG) --follow-tags

