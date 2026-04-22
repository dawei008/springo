import { useState, useCallback } from 'react';
import { useDesignStore } from '@/stores/designStore';

interface Props {
  onComplete: () => void;
}

export default function DesignSystemOnboarding({ onComplete }: Props) {
  const addDesignSystem = useDesignStore((s) => s.addDesignSystem);
  const [brandName, setBrandName] = useState('');
  const [primaryColor, setPrimaryColor] = useState('#6b5bff');
  const [font, setFont] = useState('Inter');

  const handleCreate = useCallback(() => {
    addDesignSystem({
      id: `ds-${Date.now()}`,
      brandName: brandName || 'My Brand',
      colors: {
        primary: primaryColor,
        secondary: '#f0f0f0',
        accent: primaryColor,
        background: '#ffffff',
        text: '#1a1a1a',
      },
      fonts: { heading: font, body: font },
      components: [],
      isDefault: true,
      createdAt: Date.now(),
    });
    onComplete();
  }, [brandName, primaryColor, font, addDesignSystem, onComplete]);

  return (
    <div className="ds-onboarding-overlay" onClick={onComplete}>
      <div className="ds-onboarding-modal" onClick={(e) => e.stopPropagation()}>
        <h2 className="ds-onboarding-title">{'\u2728'} Create Your Design System</h2>
        <p className="ds-onboarding-desc">
          Set up a design system to keep your designs consistent. You can always change it later.
        </p>

        <label className="ds-onboarding-field">
          <span>Brand Name</span>
          <input
            type="text"
            value={brandName}
            onChange={(e) => setBrandName(e.target.value)}
            placeholder="My Company"
            autoFocus
          />
        </label>

        <label className="ds-onboarding-field">
          <span>Primary Color</span>
          <div className="ds-onboarding-color-row">
            <input
              type="color"
              value={primaryColor}
              onChange={(e) => setPrimaryColor(e.target.value)}
              className="ds-onboarding-color-picker"
            />
            <input
              type="text"
              value={primaryColor}
              onChange={(e) => setPrimaryColor(e.target.value)}
              className="ds-onboarding-color-text"
              placeholder="#6b5bff"
            />
          </div>
        </label>

        <label className="ds-onboarding-field">
          <span>Font</span>
          <select value={font} onChange={(e) => setFont(e.target.value)}>
            <option value="Inter">Inter</option>
            <option value="SF Pro Display">SF Pro Display</option>
            <option value="Roboto">Roboto</option>
            <option value="Poppins">Poppins</option>
            <option value="Noto Sans SC">Noto Sans SC</option>
            <option value="system-ui">System Default</option>
          </select>
        </label>

        <div className="ds-onboarding-actions">
          <button className="ds-onboarding-skip" onClick={onComplete}>
            Skip for now
          </button>
          <button className="ds-onboarding-create" onClick={handleCreate}>
            Create
          </button>
        </div>
      </div>
    </div>
  );
}
