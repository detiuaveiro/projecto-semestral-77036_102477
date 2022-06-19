import pickle

from PIL import Image
import imagehash
import os
import time

image_directory = "node" + str(0)

if "backup_node0" in os.listdir(image_directory):
    print("fixe")
'''
i = 0
x = 10

start = time.time()
update = 0
while i < x and update < 5:
    time.sleep(2)
    update = time.time() - start
    print(update)
    i += 1
'''