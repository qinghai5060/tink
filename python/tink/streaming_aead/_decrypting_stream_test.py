# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for tink.python.tink.streaming_aead.decrypting_stream."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import io
from typing import BinaryIO

from absl.testing import absltest
from absl.testing.absltest import mock

from tink import core
from tink.cc.pybind import tink_bindings
from tink.streaming_aead import _decrypting_stream

# Using malformed UTF-8 sequences to ensure there is no accidental decoding.
B_X80 = b'\x80'
B_SOMETHING_ = b'somethin' + B_X80
B_AAD_ = b'aa' + B_X80


class FakeInputStreamAdapter(object):

  def __init__(self, file_object_adapter):
    self._adapter = file_object_adapter

  @core.use_tink_errors
  def read(self, size=-1):
    try:
      if size < 0:
        size = 100
      return self._adapter.read(size)
    except EOFError:
      not_ok = tink_bindings.StatusNotOk()
      not_ok.status = tink_bindings.Status(
          tink_bindings.ErrorCode.OUT_OF_RANGE,
          'Reached end of stream.')
      raise not_ok


def fake_get_input_stream_adapter(self, cc_primitive, aad, source):
  del cc_primitive, aad, self  # unused
  return FakeInputStreamAdapter(source)


def get_raw_decrypting_stream(
    ciphertext_source: BinaryIO,
    aad: bytes,
    close_ciphertext_source: bool = True) -> io.RawIOBase:
  return _decrypting_stream.RawDecryptingStream(
      None, ciphertext_source, aad,
      close_ciphertext_source=close_ciphertext_source)


class DecryptingStreamTest(absltest.TestCase):

  def setUp(self):
    super(DecryptingStreamTest, self).setUp()
    # Replace the DecryptingStream's staticmethod with a custom function to
    # avoid the need for a Streaming AEAD primitive.
    self.addCleanup(mock.patch.stopall)
    mock.patch.object(
        _decrypting_stream.RawDecryptingStream,
        '_get_input_stream_adapter',
        new=fake_get_input_stream_adapter).start()

  def test_non_readable_object(self):
    f = mock.Mock()
    f.readable = mock.Mock(return_value=False)

    with self.assertRaisesRegex(ValueError, 'readable'):
      get_raw_decrypting_stream(f, B_AAD_)

  def test_read(self):
    f = io.BytesIO(B_SOMETHING_)
    ds = get_raw_decrypting_stream(f, B_AAD_)

    self.assertEqual(ds.read(9), B_SOMETHING_)

  def test_readinto(self):
    f = io.BytesIO(B_SOMETHING_)
    ds = get_raw_decrypting_stream(f, B_AAD_)

    b = bytearray(9)
    self.assertEqual(ds.readinto(b), 9)
    self.assertEqual(bytes(b), B_SOMETHING_)

  def test_read_until_eof(self):
    f = io.BytesIO(B_SOMETHING_)
    ds = get_raw_decrypting_stream(f, B_AAD_)

    self.assertEqual(ds.read(), B_SOMETHING_)

  def test_read_eof_reached(self):
    f = io.BytesIO()
    ds = get_raw_decrypting_stream(f, B_AAD_)

    self.assertEqual(ds.read(), b'')

  def test_unsupported_operation(self):
    f = io.BytesIO(B_SOMETHING_)
    ds = get_raw_decrypting_stream(f, B_AAD_)

    with self.assertRaises(io.UnsupportedOperation):
      ds.seek(0, 0)
    with self.assertRaises(io.UnsupportedOperation):
      ds.tell()
    with self.assertRaises(io.UnsupportedOperation):
      ds.truncate()
    with self.assertRaises(io.UnsupportedOperation):
      ds.write(b'data')
    with self.assertRaises(io.UnsupportedOperation):
      ds.writelines([b'data'])
    with self.assertRaises(io.UnsupportedOperation):
      ds.fileno()

  def test_closed(self):
    f = io.BytesIO(B_SOMETHING_)
    ds = get_raw_decrypting_stream(f, B_AAD_)

    self.assertFalse(ds.closed)
    self.assertFalse(f.closed)
    ds.close()
    self.assertTrue(ds.closed)
    self.assertTrue(f.closed)
    ds.close()

  def test_close_ciphertext_source_false(self):
    f = io.BytesIO(B_SOMETHING_)
    ds = get_raw_decrypting_stream(f, B_AAD_, close_ciphertext_source=False)

    self.assertFalse(ds.closed)
    self.assertFalse(f.closed)
    ds.close()
    self.assertTrue(ds.closed)
    self.assertFalse(f.closed)
    ds.close()

  def test_closed_methods_raise(self):
    f = io.BytesIO(B_SOMETHING_)
    ds = get_raw_decrypting_stream(f, B_AAD_)

    ds.close()
    with self.assertRaisesRegex(ValueError, 'closed'):
      ds.read()
    with self.assertRaisesRegex(ValueError, 'closed'):
      ds.flush()

  def test_inquiries(self):
    f = io.BytesIO(B_SOMETHING_)
    ds = get_raw_decrypting_stream(f, B_AAD_)

    self.assertTrue(ds.readable())
    self.assertFalse(ds.writable())
    self.assertFalse(ds.seekable())
    self.assertFalse(ds.isatty())

  def test_context_manager(self):
    f = io.BytesIO(B_SOMETHING_)

    with get_raw_decrypting_stream(f, B_AAD_) as ds:
      self.assertEqual(ds.read(), B_SOMETHING_)
    self.assertTrue(ds.closed)


if __name__ == '__main__':
  absltest.main()
