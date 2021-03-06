#!/usr/bin/bash

set -ex

export PATH=$PATH:/sbin/:/usr/sbin/

[[ -n "$SQUASHFS_URL" ]] && make image-install SQUASHFS_URL=$SQUASHFS_URL || make image-install

IMG="$(make verrel).squashfs.img"
ln -v ovirt-node-appliance.squashfs.img $IMG

# Create an index file for imgbase remote
ls -1 > .index

# Don't fail when make check fails
# Because teh build succeeded, we just want to see how good the image is
make check || :
