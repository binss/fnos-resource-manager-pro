"""Generate the project's own fallback PNG icon using Python's standard library."""
from pathlib import Path
import math
import struct
import zlib


def make_png(size):
    points = [(30, 162), (65, 158), (89, 94), (122, 147), (149, 62), (176, 113), (224, 84)]
    def distance(x, y, a, b):
        dx, dy = b[0]-a[0], b[1]-a[1]
        t = max(0, min(1, ((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)))
        return math.hypot(x-a[0]-t*dx, y-a[1]-t*dy)
    rows = bytearray()
    for row in range(size):
        rows.append(0)
        y = (row+.5)*256/size
        for col in range(size):
            x = (col+.5)*256/size
            qx, qy = max(52-x, 0, x-204), max(52-y, 0, y-204)
            inside = 8<=x<=248 and 8<=y<=248 and qx*qx+qy*qy<=44*44
            color = (0,0,0,0) if not inside else (20, int(115-y*.08), int(238-y*.08),255)
            if inside and min(distance(x,y,a,b) for a,b in zip(points,points[1:]))<=4:
                color = (255,255,255,255)
            rows.extend(color)
    def chunk(kind, data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b'')


def generate(root):
    package=root/'packages/resmonpro'
    for name,size in [('ICON.PNG',64),('ICON_256.PNG',256),('app/ui/images/icon_64.png',64),('app/ui/images/icon_256.png',256)]:
        (package/name).write_bytes(make_png(size))

if __name__=='__main__':
    generate(Path(__file__).resolve().parents[1])
