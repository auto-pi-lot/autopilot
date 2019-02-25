"""
Setup a digital scale...

Warning:
    Not implemented yet
"""

import argparse
import os
import subprocess
import getpass

if __name__ == "__main__":

    if os.getuid() != 0:
        raise Exception("Need to run as root")

    parser = argparse.ArgumentParser(description="Setup a USB-HID scale for the terminal")
    parser.add_argument('-v', '--vendor', help="Vendor ID for scale, default is 0x1446 (stamps.com scale)")
    parser.add_argument('-p', '--product', help="Product ID for scale, default is 0x6a73 (stamps.com scale")

    args = parser.parse_args()

    # Parse Arguments and assign defaults
    if args.vendor:
        vendor = args.vendor
    else:
        vendor = "0x1446"

    if args.product:
        product = args.product
    else:
        product = "0x6a73"

    # make rule string
    rule_string = 'ACTION=="add", SUBSYSTEMS=="usb", BUS=="usb", ATTR{{idVendor}}=="{}", ATTR{{idProduct}}=="{}", MODE=="0666", GROUP=="scale"'.format(vendor, product)

    # create udev rule
    rule_fn = '/etc/udev/rules.d/10-local.rules'
    if os.path.exists(rule_fn):
        mode = "r+"
    else:
        mode = "w"

    with open(rule_fn, mode=mode) as udev_rule:
        udev_rule.write(rule_string)

    print('wrote rule: \n{} to file: \n{}'.format(rule_string, rule_fn))
    print('adding user to "scale" group')

    username = getpass.getuser()
    subprocess.call(['adduser',username,'scale'])


    print('added to group, restarting udev')
    subprocess.call(['sudo', 'groupadd', 'scale'])
    subprocess.call(['sudo', 'service', 'udev', 'restart'])

    print('scale set up! unplug and replug your scale!')





