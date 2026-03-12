"""
HandScribe Synthesis Model
Style-conditioned handwriting character generator using a CVAE-GAN architecture.

Architecture:
  - Encoder: extracts style embedding from reference glyph images
  - Generator: synthesizes new glyphs conditioned on (char_class, style_vec)
  - Discriminator: real/fake + style consistency loss

Training data: IAM Handwriting Database + EMNIST
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)

GLYPH_SIZE = 64     # px
STYLE_DIM = 128     # style embedding dimension
NOISE_DIM = 64      # latent noise dimension
NUM_CHARS = 80      # character classes


# ─── Style Encoder ─────────────────────────────────────────────────────────────

class StyleEncoder(nn.Module):
    """
    Encodes reference glyph images into a compact style embedding.
    Input: N × 1 × 64 × 64 reference glyphs
    Output: 128-dim style vector
    """

    def __init__(self, style_dim: int = STYLE_DIM):
        super().__init__()
        self.cnn = nn.Sequential(
            # Block 1
            nn.Conv2d(1, 32, 3, padding=1), nn.BatchNorm2d(32), nn.LeakyReLU(0.2),
            nn.Conv2d(32, 32, 3, padding=1), nn.BatchNorm2d(32), nn.LeakyReLU(0.2),
            nn.MaxPool2d(2),  # 32×32

            # Block 2
            nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.LeakyReLU(0.2),
            nn.Conv2d(64, 64, 3, padding=1), nn.BatchNorm2d(64), nn.LeakyReLU(0.2),
            nn.MaxPool2d(2),  # 16×16

            # Block 3
            nn.Conv2d(64, 128, 3, padding=1), nn.BatchNorm2d(128), nn.LeakyReLU(0.2),
            nn.Conv2d(128, 128, 3, padding=1), nn.BatchNorm2d(128), nn.LeakyReLU(0.2),
            nn.AdaptiveAvgPool2d((4, 4)),  # 4×4
        )
        self.fc_mu = nn.Linear(128 * 4 * 4, style_dim)
        self.fc_logvar = nn.Linear(128 * 4 * 4, style_dim)

    def forward(self, x: torch.Tensor) -> tuple:
        # Average over multiple reference glyphs (N, C, H, W) → (1, C, H, W)
        if x.dim() == 5:
            B, N, C, H, W = x.shape
            x = x.view(B * N, C, H, W)
            feats = self.cnn(x).view(B * N, -1)
            feats = feats.view(B, N, -1).mean(dim=1)
        else:
            feats = self.cnn(x).view(x.size(0), -1)

        mu = self.fc_mu(feats)
        logvar = self.fc_logvar(feats)
        return mu, logvar

    def reparameterize(self, mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        if self.training:
            std = torch.exp(0.5 * logvar)
            eps = torch.randn_like(std)
            return mu + eps * std
        return mu


# ─── Generator ─────────────────────────────────────────────────────────────────

class GlyphGenerator(nn.Module):
    """
    Generates a glyph image conditioned on character class + style embedding.
    Output: 1 × 64 × 64 grayscale glyph
    """

    def __init__(self, num_chars: int = NUM_CHARS, style_dim: int = STYLE_DIM, noise_dim: int = NOISE_DIM):
        super().__init__()
        self.char_embed = nn.Embedding(num_chars, 64)
        in_dim = 64 + style_dim + noise_dim

        self.fc = nn.Sequential(
            nn.Linear(in_dim, 512),
            nn.BatchNorm1d(512), nn.ReLU(),
            nn.Linear(512, 128 * 4 * 4),
            nn.BatchNorm1d(128 * 4 * 4), nn.ReLU(),
        )

        self.deconv = nn.Sequential(
            # 4×4 → 8×8
            nn.ConvTranspose2d(128, 128, 4, 2, 1), nn.BatchNorm2d(128), nn.ReLU(),
            # 8×8 → 16×16
            nn.ConvTranspose2d(128, 64, 4, 2, 1), nn.BatchNorm2d(64), nn.ReLU(),
            # 16×16 → 32×32
            nn.ConvTranspose2d(64, 32, 4, 2, 1), nn.BatchNorm2d(32), nn.ReLU(),
            # 32×32 → 64×64
            nn.ConvTranspose2d(32, 1, 4, 2, 1), nn.Sigmoid(),
        )

    def forward(self, char_idx: torch.Tensor, style: torch.Tensor, noise: Optional[torch.Tensor] = None) -> torch.Tensor:
        B = char_idx.size(0)
        if noise is None:
            noise = torch.randn(B, NOISE_DIM, device=char_idx.device)

        char_emb = self.char_embed(char_idx)
        z = torch.cat([char_emb, style, noise], dim=1)
        h = self.fc(z).view(B, 128, 4, 4)
        return self.deconv(h)


# ─── Discriminator ─────────────────────────────────────────────────────────────

class GlyphDiscriminator(nn.Module):
    """
    Classifies glyphs as real/fake and checks style consistency.
    """

    def __init__(self, num_chars: int = NUM_CHARS, style_dim: int = STYLE_DIM):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 32, 4, 2, 1), nn.LeakyReLU(0.2),   # 32×32
            nn.Conv2d(32, 64, 4, 2, 1), nn.BatchNorm2d(64), nn.LeakyReLU(0.2),  # 16×16
            nn.Conv2d(64, 128, 4, 2, 1), nn.BatchNorm2d(128), nn.LeakyReLU(0.2),  # 8×8
            nn.Conv2d(128, 256, 4, 2, 1), nn.BatchNorm2d(256), nn.LeakyReLU(0.2),  # 4×4
            nn.AdaptiveAvgPool2d(1),
        )
        self.fc_real = nn.Linear(256, 1)
        self.fc_char = nn.Linear(256, num_chars)
        self.fc_style = nn.Linear(256, style_dim)

    def forward(self, x: torch.Tensor) -> tuple:
        feats = self.cnn(x).view(x.size(0), -1)
        return (
            self.fc_real(feats),   # real/fake logit
            self.fc_char(feats),   # char class logit
            self.fc_style(feats),  # predicted style
        )


# ─── Full Synthesis System ─────────────────────────────────────────────────────

class HandwritingSynthesizer:
    """
    High-level interface for:
    1. Training on a corpus
    2. Synthesizing missing glyphs
    3. Rendering text sequences
    """

    CHAR_VOCAB = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
                      "0123456789.,!?'\"()-;:@#%&*+=/<>[] \t\n")

    def __init__(self, model_dir: str = "data/models"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.encoder = StyleEncoder().to(self.device)
        self.generator = GlyphGenerator().to(self.device)
        self.discriminator = GlyphDiscriminator().to(self.device)

        self.char2idx = {c: i for i, c in enumerate(self.CHAR_VOCAB)}
        self.style_cache: Optional[torch.Tensor] = None

        self._try_load_checkpoint()

    def _try_load_checkpoint(self):
        ckpt = self.model_dir / "handscribe_model.pt"
        if ckpt.exists():
            try:
                state = torch.load(ckpt, map_location=self.device)
                self.encoder.load_state_dict(state["encoder"])
                self.generator.load_state_dict(state["generator"])
                logger.info(f"Loaded checkpoint from {ckpt}")
            except Exception as e:
                logger.warning(f"Could not load checkpoint: {e}")

    def encode_style(self, reference_glyphs: Dict[str, List[np.ndarray]]) -> torch.Tensor:
        """
        Build a style embedding from reference glyph images.
        Takes the best-sampled glyphs and encodes them.
        """
        self.encoder.eval()
        all_imgs = []
        for imgs in reference_glyphs.values():
            all_imgs.extend(imgs[:3])  # up to 3 per char

        if not all_imgs:
            logger.warning("No reference glyphs — using zero style")
            self.style_cache = torch.zeros(1, STYLE_DIM, device=self.device)
            return self.style_cache

        tensors = [torch.tensor(img, dtype=torch.float32).unsqueeze(0) for img in all_imgs]
        batch = torch.stack(tensors).to(self.device)  # N × 1 × H × W

        with torch.no_grad():
            mu, logvar = self.encoder(batch)
            style = self.encoder.reparameterize(mu, logvar)
            self.style_cache = style.mean(dim=0, keepdim=True)

        return self.style_cache

    def synthesize_glyph(self, char: str, style: Optional[torch.Tensor] = None) -> np.ndarray:
        """Generate a single glyph in the learned style."""
        self.generator.eval()
        if style is None:
            style = self.style_cache or torch.zeros(1, STYLE_DIM, device=self.device)

        char_idx = self.char2idx.get(char, 0)
        char_tensor = torch.tensor([char_idx], device=self.device)

        with torch.no_grad():
            glyph = self.generator(char_tensor, style)

        return glyph.squeeze().cpu().numpy()

    def render_text(self, text: str, line_width_px: int = 800) -> np.ndarray:
        """
        Render a full text string as a handwriting image.
        Returns: RGB numpy array (H × W × 3)
        """
        if self.style_cache is None:
            logger.warning("No style set — using default")
            self.style_cache = torch.zeros(1, STYLE_DIM, device=self.device)

        lines = self._wrap_text(text, line_width_px)
        line_height = GLYPH_SIZE + 12
        canvas_h = max(len(lines) * line_height + 40, 200)

        canvas = np.ones((canvas_h, line_width_px), dtype=np.float32)

        for line_idx, line in enumerate(lines):
            y_offset = 20 + line_idx * line_height
            x_offset = 20

            for char in line:
                if x_offset + GLYPH_SIZE > line_width_px - 20:
                    break
                glyph = self.synthesize_glyph(char)
                # Invert: white background, dark ink
                ink = 1.0 - glyph
                canvas[y_offset:y_offset + GLYPH_SIZE, x_offset:x_offset + GLYPH_SIZE] = (
                    np.minimum(canvas[y_offset:y_offset + GLYPH_SIZE, x_offset:x_offset + GLYPH_SIZE], 1.0 - ink)
                )
                x_offset += GLYPH_SIZE + 4  # inter-character spacing

        # Convert to RGB uint8
        rgb = (canvas * 255).astype(np.uint8)
        rgb = np.stack([rgb, rgb, rgb], axis=2)
        return rgb

    def _wrap_text(self, text: str, width_px: int) -> List[str]:
        chars_per_line = max(1, (width_px - 40) // (GLYPH_SIZE + 4))
        words = text.split(" ")
        lines = []
        current = ""

        for word in words:
            test = (current + " " + word).strip()
            if len(test) <= chars_per_line:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word

        if current:
            lines.append(current)

        return lines if lines else [text[:chars_per_line]]

    def train_on_corpus(
        self,
        glyph_library: Dict[str, List[np.ndarray]],
        epochs: int = 50,
        lr: float = 2e-4,
        batch_size: int = 32
    ):
        """
        Fine-tune the model on a user's glyph library.
        Uses a CVAE-GAN training loop.

        For training from scratch, download IAM Handwriting DB first.
        See: https://fki.tic.heia-fr.ch/databases/iam-handwriting-database
        """
        from torch.optim import Adam

        opt_G = Adam(list(self.encoder.parameters()) + list(self.generator.parameters()), lr=lr, betas=(0.5, 0.999))
        opt_D = Adam(self.discriminator.parameters(), lr=lr * 0.5, betas=(0.5, 0.999))

        self.encoder.train(); self.generator.train(); self.discriminator.train()

        dataset = self._build_dataset(glyph_library)
        logger.info(f"Training on {len(dataset)} glyph pairs for {epochs} epochs")

        for epoch in range(epochs):
            np.random.shuffle(dataset)
            d_losses, g_losses = [], []

            for i in range(0, len(dataset), batch_size):
                batch = dataset[i:i + batch_size]
                if len(batch) < 2:
                    continue

                real_imgs = torch.stack([torch.tensor(b[0]) for b in batch]).unsqueeze(1).to(self.device)
                char_idxs = torch.tensor([b[1] for b in batch], device=self.device)

                # ─ Train Discriminator ─
                mu, logvar = self.encoder(real_imgs)
                style = self.encoder.reparameterize(mu, logvar)
                fake = self.generator(char_idxs, style)

                real_pred, _, _ = self.discriminator(real_imgs)
                fake_pred, _, _ = self.discriminator(fake.detach())

                d_loss = F.binary_cross_entropy_with_logits(real_pred, torch.ones_like(real_pred)) + \
                         F.binary_cross_entropy_with_logits(fake_pred, torch.zeros_like(fake_pred))

                opt_D.zero_grad(); d_loss.backward(); opt_D.step()

                # ─ Train Generator ─
                fake_pred2, char_pred, style_pred = self.discriminator(fake)
                g_adv = F.binary_cross_entropy_with_logits(fake_pred2, torch.ones_like(fake_pred2))
                g_char = F.cross_entropy(char_pred, char_idxs)
                kl = -0.5 * torch.mean(1 + logvar - mu.pow(2) - logvar.exp())

                g_loss = g_adv + 0.5 * g_char + 0.01 * kl

                opt_G.zero_grad(); g_loss.backward(); opt_G.step()
                d_losses.append(d_loss.item()); g_losses.append(g_loss.item())

            if (epoch + 1) % 10 == 0:
                logger.info(f"Epoch {epoch+1}/{epochs} | D: {np.mean(d_losses):.4f} | G: {np.mean(g_losses):.4f}")

        self._save_checkpoint()
        logger.info("Training complete!")

    def _build_dataset(self, glyph_library: Dict[str, List[np.ndarray]]) -> List:
        dataset = []
        for char, imgs in glyph_library.items():
            idx = self.char2idx.get(char, 0)
            for img in imgs:
                if img.shape == (GLYPH_SIZE, GLYPH_SIZE):
                    dataset.append((img.astype(np.float32), idx))
        return dataset

    def _save_checkpoint(self):
        ckpt = self.model_dir / "handscribe_model.pt"
        torch.save({
            "encoder": self.encoder.state_dict(),
            "generator": self.generator.state_dict(),
        }, ckpt)
        logger.info(f"Checkpoint saved to {ckpt}")
