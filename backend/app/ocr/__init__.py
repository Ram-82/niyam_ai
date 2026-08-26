"""OCR — extract structured invoice fields from an uploaded PDF or photo.

P2.1 Step 1 ships the mock adapter only. Real extraction (pdfminer for
text-native PDFs, tesseract for scanned images) lands in a later step.
The public surface stays stable: callers use :func:`service.extract`
and receive an :class:`~app.ocr.types.InvoiceExtraction`.
"""
