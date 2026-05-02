from pathlib import Path


def decrypt_pdf(encrypted_path: Path, password: str, output_path: Path) -> Path:
    """Decrypt a password-protected PDF using pikepdf and save to output_path."""
    import pikepdf

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pikepdf.open(str(encrypted_path), password=password) as pdf:
        pdf.save(str(output_path))
    return output_path
