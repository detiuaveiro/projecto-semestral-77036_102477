from PIL import Image
import imagehash
import os

'''
image_directory = "./node" + str(0)

for image in os.listdir(image_directory):
    path = image_directory + '/' + image
    hash = str(imagehash.phash(Image.open(path)))
    print(path)
    print(hash)
'''

img_path = "./node0/010_Aveiro.jpg"
image = Image.open(img_path)
print(image.tobytes())