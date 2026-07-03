#!/bin/sh

rm ../build/quiet-backup_*
dpkg-buildpackage -us -uc -tc
mv ../quiet-backup_* ../build