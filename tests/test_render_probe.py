import struct
import sys
from pathlib import Path
import unittest
import zlib
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from render_probe import frame_pixels, png_bytes

class PixelTests(unittest.TestCase):
    def report(self):
        return dict(status='completed', exit_code=0, logs_dropped=0,
                    graphics=dict(contexts=1, draw_calls=1, shader_compiles=2, pixel_reads=1, backend='egl-surfaceless-pbuffer'),
                    logs=[dict(text='FRAME_RGBA8 1 2'), dict(text='ROW 0 ff0000ff'), dict(text='ROW 1 00ff00ff')])
    def test_flip_matches_gl_origin(self):
        self.assertEqual(frame_pixels(self.report()), (1, 2, b'\0\xff\0\xff\0\0'))
    def test_missing_or_duplicate_row_rejected(self):
        for logs in [[dict(text='FRAME_RGBA8 1 2'),dict(text='ROW 0 ff0000ff')],
                     [dict(text='FRAME_RGBA8 1 2'),dict(text='ROW 0 ff0000ff'),dict(text='ROW 0 ff0000ff')]]:
            r=self.report();r['logs']=logs
            with self.assertRaises(ValueError):frame_pixels(r)
    def test_row_and_frame_bounds(self):
        for text in ['ROW 9 ff0000ff','ROW 0 xx0000ff','ROW 0 ff00','ROW -1 ff0000ff']:
            r=self.report();r['logs'][1]['text']=text
            with self.assertRaises(ValueError):frame_pixels(r)
    def test_failed_or_truncated_renderer_rejected(self):
        for patch in [dict(status='timeout'),dict(exit_code=2),dict(logs_dropped=1)]:
            r=self.report();r.update(patch)
            with self.assertRaises(ValueError):frame_pixels(r)
    def test_no_pixels_without_native_drawing_evidence(self):
        r=self.report();r['graphics']['draw_calls']=0
        with self.assertRaises(ValueError):frame_pixels(r)
    def test_png_chunks_crc_and_pixel_bytes(self):
        rgb=b'\0\xff\0\xff\0\0';data=png_bytes(1,2,rgb)
        self.assertTrue(data.startswith(b'\x89PNG\r\n\x1a\n'));offset=8;chunks={}
        while offset<len(data):
            size=struct.unpack_from('>I',data,offset)[0];kind=data[offset+4:offset+8]
            body=data[offset+8:offset+8+size];crc=struct.unpack_from('>I',data,offset+8+size)[0]
            self.assertEqual(crc,zlib.crc32(kind+body));chunks[kind]=body;offset+=size+12
        self.assertEqual(zlib.decompress(chunks[b'IDAT']),b'\0'+rgb[:3]+b'\0'+rgb[3:])
        self.assertEqual(chunks[b'IEND'],b'')
    def test_png_invalid_length_rejected(self):
        with self.assertRaises(ValueError):png_bytes(2,2,b'123')

if __name__=='__main__':unittest.main()
