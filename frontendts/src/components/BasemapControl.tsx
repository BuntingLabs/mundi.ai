// Copyright (C) 2025 Bunting Labs, Inc.

// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.

// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

import { type IControl, type Map as MLMap } from 'maplibre-gl';

export class BasemapControl implements IControl {
  private _container: HTMLDivElement | undefined;
  private _button: HTMLButtonElement | undefined;
  private _menu: HTMLDivElement | undefined;
  private _availableBasemaps: string[];
  private _currentBasemap: string;
  private _onBasemapChange: (basemap: string) => void;
  private _displayNames: Record<string, string>;
  private _isMenuOpen: boolean = false;

  constructor(
    availableBasemaps: string[],
    currentBasemap: string,
    displayNames: Record<string, string>,
    onBasemapChange: (basemap: string) => void,
  ) {
    this._availableBasemaps = availableBasemaps;
    this._currentBasemap = currentBasemap;
    this._displayNames = displayNames;
    this._onBasemapChange = onBasemapChange;
  }

  onAdd(_map: MLMap): HTMLElement {
    this._container = document.createElement('div');
    this._container.className = 'maplibregl-ctrl maplibregl-ctrl-group';
    this._container.style.position = 'relative';

    // Create button
    const button = document.createElement('button');
    this._button = button;
    button.className = 'maplibregl-ctrl-basemap';
    button.type = 'button';
    button.title = 'Choose basemap';
    button.setAttribute('aria-label', 'Choose basemap');
    button.setAttribute('aria-expanded', 'false');

    // Create globe icon (SVG)
    button.innerHTML = `
      <svg width="20" height="20" viewBox="0 0 24 24" fill="#333">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.94-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
      </svg>
    `;
    button.style.border = 'none';
    button.style.background = 'transparent';
    button.style.cursor = 'pointer';
    button.style.padding = '5px';
    button.style.display = 'flex';
    button.style.alignItems = 'center';
    button.style.justifyContent = 'center';

    button.addEventListener('click', this._onClickButton.bind(this));

    // Create dropdown menu with image previews
    const menu = document.createElement('div');
    this._menu = menu;
    menu.className = 'maplibregl-ctrl-basemap-menu';
    menu.style.position = 'absolute';
    menu.style.top = '100%';
    menu.style.right = '0';
    menu.style.marginTop = '5px';
    menu.style.backgroundColor = 'oklch(27.8% 0.033 256.848)';
    menu.style.border = '1px solid oklch(1 0 0 / 15%)';
    menu.style.borderRadius = '6px';
    menu.style.boxShadow = '0 4px 20px rgba(0,0,0,0.15)';
    menu.style.padding = '8px';
    menu.style.zIndex = '1000';
    menu.style.display = 'none';
    menu.style.width = '280px';
    menu.style.gridTemplateColumns = 'repeat(2, 120px)';
    menu.style.gap = '8px';
    menu.style.justifyContent = 'center';

    // Create menu items with image previews
    this._availableBasemaps.forEach((basemap) => {
      const item = document.createElement('button');
      item.className = 'maplibregl-ctrl-basemap-item';
      item.style.display = 'block';
      item.style.width = '120px';
      item.style.height = '120px';
      item.style.padding = '0';
      item.style.background = 'transparent';
      item.style.cursor = 'pointer';
      item.style.borderRadius = '4px';
      item.style.overflow = 'hidden';
      item.style.position = 'relative';
      item.style.border = '1px solid rgba(255, 255, 255, 0.2)'; // Light border for non-selected

      // Create image container
      const imageContainer = document.createElement('div');
      imageContainer.style.position = 'relative';
      imageContainer.style.width = '100%';
      imageContainer.style.height = '100%';
      imageContainer.style.backgroundColor = '#f5f5f5';

      // Create preview image
      const img = document.createElement('img');
      img.style.width = '100%';
      img.style.height = '100%';
      img.style.objectFit = 'cover';
      img.style.display = 'block';

      // Create loading placeholder
      const loading = document.createElement('div');
      loading.style.position = 'absolute';
      loading.style.top = '50%';
      loading.style.left = '50%';
      loading.style.transform = 'translate(-50%, -50%)';
      loading.style.fontSize = '10px';
      loading.style.color = '#666';
      loading.textContent = 'Loading...';
      imageContainer.appendChild(loading);

      // Create basemap name overlay
      const nameOverlay = document.createElement('div');
      nameOverlay.style.position = 'absolute';
      nameOverlay.style.bottom = '0';
      nameOverlay.style.left = '0';
      nameOverlay.style.right = '0';
      nameOverlay.style.background = 'linear-gradient(transparent, rgba(0,0,0,0.7))';
      nameOverlay.style.color = 'white';
      nameOverlay.style.padding = '10px 8px 6px';
      nameOverlay.style.fontSize = '10px';
      nameOverlay.style.fontWeight = 'bold';
      nameOverlay.style.textAlign = 'center';
      nameOverlay.textContent = this._getBasemapDisplayName(basemap);

      // Highlight current basemap
      if (basemap === this._currentBasemap) {
        item.style.borderColor = '#007cff'; // Selected blue
      }

      // Hover styles
      item.addEventListener('mouseenter', () => {
        if (basemap !== this._currentBasemap) {
          item.style.borderColor = '#4da3ff'; // Lighter blue on hover
        }
      });
      item.addEventListener('mouseleave', () => {
        if (basemap !== this._currentBasemap) {
          item.style.borderColor = 'rgba(255, 255, 255, 0.2)'; // Light border for non-selected
        }
      });

      item.addEventListener('click', (e) => {
        e.stopPropagation();
        this._selectBasemap(basemap);
      });

      imageContainer.appendChild(img);
      imageContainer.appendChild(nameOverlay);
      item.appendChild(imageContainer);
      menu.appendChild(item);

      // Load basemap preview image
      this._loadBasemapPreview(img, loading, basemap);
    });

    // Close menu when clicking outside
    document.addEventListener('click', this._onDocumentClick.bind(this));

    this._container.appendChild(button);
    this._container.appendChild(menu);
    return this._container;
  }

  onRemove(): void {
    document.removeEventListener('click', this._onDocumentClick.bind(this));
    if (this._container && this._container.parentNode) {
      this._container.parentNode.removeChild(this._container);
    }
  }

  private _getBasemapDisplayName(basemap: string): string {
    return this._displayNames[basemap] || basemap;
  }

  private _onClickButton(e: Event): void {
    e.stopPropagation();
    this._toggleMenu();
  }

  private _onDocumentClick(): void {
    if (this._isMenuOpen) {
      this._closeMenu();
    }
  }

  private _toggleMenu(): void {
    if (this._isMenuOpen) {
      this._closeMenu();
    } else {
      this._openMenu();
    }
  }

  private _openMenu(): void {
    if (!this._menu || !this._button) return;

    this._menu.style.display = 'grid';
    this._isMenuOpen = true;
    this._button.setAttribute('aria-expanded', 'true');
  }

  private _closeMenu(): void {
    if (!this._menu || !this._button) return;

    this._menu.style.display = 'none';
    this._isMenuOpen = false;
    this._button.setAttribute('aria-expanded', 'false');
  }

  private _selectBasemap(basemap: string): void {
    this._currentBasemap = basemap;
    this._onBasemapChange(basemap);
    this._closeMenu();
    this._updateMenuItems();
  }

  private _loadBasemapPreview(img: HTMLImageElement, loading: HTMLElement, basemap: string): void {
    const url = new URL('/api/basemaps/render.png', window.location.origin);
    url.searchParams.set('basemap', basemap);

    img.onload = () => {
      loading.style.display = 'none';
    };

    img.onerror = () => {
      loading.textContent = 'Error';
      loading.style.color = '#ff6b6b';
    };

    img.src = url.toString();
  }

  private _updateMenuItems(): void {
    if (!this._menu) return;

    const items = this._menu.querySelectorAll('.maplibregl-ctrl-basemap-item');
    items.forEach((item, index) => {
      const basemap = this._availableBasemaps[index];
      const htmlItem = item as HTMLElement;

      if (basemap === this._currentBasemap) {
        htmlItem.style.borderColor = '#007cff'; // Selected blue
      } else {
        htmlItem.style.borderColor = 'rgba(255, 255, 255, 0.2)'; // Light border for non-selected
      }
    });
  }

  updateBasemap(basemap: string): void {
    this._currentBasemap = basemap;
    this._updateMenuItems();
  }

  updateCallback(onBasemapChange: (basemap: string) => void): void {
    this._onBasemapChange = onBasemapChange;
  }

  refreshPreviews(): void {
    if (!this._menu) return;

    const items = this._menu.querySelectorAll('.maplibregl-ctrl-basemap-item');
    items.forEach((item, index) => {
      const basemap = this._availableBasemaps[index];
      const img = item.querySelector('img') as HTMLImageElement;
      const loading = item.querySelector('div[style*="Loading"]') as HTMLElement;

      if (img && loading) {
        loading.style.display = 'block';
        loading.textContent = 'Loading...';
        loading.style.color = '#666';
        this._loadBasemapPreview(img, loading, basemap);
      }
    });
  }
}
