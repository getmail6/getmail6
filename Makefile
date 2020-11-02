.PHONY: doc test check push dist up tag

# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

doc:
	links -dump docs/documentation.html > docs/documentation.txt
	links -dump docs/configuration.html > docs/configuration.txt
	links -dump docs/faq.html > docs/faq.txt
	links -dump docs/troubleshooting.html > docs/troubleshooting.txt

test:
	# this is a private system test
	sudo freshclam
	pip install --user .
	bash ~/mine/mailwizard/test/test_getmail.sh

check:
	/usr/bin/man -l docs/getmail.1
	restview --long-description --strict

dist: doc
	sudo python setup.py bdist_wheel

up:
	twine upload dist/`ls dist -rt | tail -1`

tag:
	$(eval TAGMSG="v$(shell ./getmail --version | cut -d ' ' -f 2)")
	echo $(TAGMSG)
	git tag -s $(TAGMSG) -m"$(TAGMSG)"
	git verify-tag $(TAGMSG)
	git push origin $(TAGMSG) --follow-tags

