export interface DesignTemplate {
  id: string;
  name: string;
  category: 'mobile' | 'web' | 'slides' | 'component';
  description: string;
  prompt: string;
}

export const DESIGN_TEMPLATES: DesignTemplate[] = [
  {
    id: 'mobile-ios',
    name: 'iOS App',
    category: 'mobile',
    description: 'iPhone frame with tab bar, status bar, and navigation',
    prompt: 'Design an iOS mobile app with iPhone 15 frame (390x844), dynamic island, status bar, bottom tab navigation with 4 tabs, and a home screen. Use SF Pro-inspired typography and iOS design patterns.',
  },
  {
    id: 'mobile-android',
    name: 'Android App',
    category: 'mobile',
    description: 'Material Design 3 mobile app with navigation bar',
    prompt: 'Design an Android app following Material Design 3 guidelines. Include a top app bar, floating action button, bottom navigation bar with 4 destinations, and a home screen with cards.',
  },
  {
    id: 'web-dashboard',
    name: 'Dashboard',
    category: 'web',
    description: 'Analytics dashboard with sidebar, charts, and KPI cards',
    prompt: 'Design a modern analytics dashboard with a collapsible sidebar navigation, top header with search and user avatar, KPI metric cards row, a main area chart, and a recent activity table. Use a professional color palette.',
  },
  {
    id: 'web-landing',
    name: 'Landing Page',
    category: 'web',
    description: 'Marketing landing page with hero, features, and CTA',
    prompt: 'Design a conversion-focused landing page with: hero section (headline, subline, CTA button, hero image placeholder), social proof logos row, 3-column feature grid with icons, testimonial carousel, pricing table, and footer. Import a distinctive Google Font.',
  },
  {
    id: 'web-saas',
    name: 'SaaS App',
    category: 'web',
    description: 'Multi-page SaaS application with settings and data views',
    prompt: 'Design a SaaS application interface with sidebar navigation (Dashboard, Projects, Team, Settings), a project list view with filters and search, a detail panel that slides in from the right, and working tab navigation between views.',
  },
  {
    id: 'slides-pitch',
    name: 'Pitch Deck',
    category: 'slides',
    description: '10-slide startup pitch deck with slide navigation',
    prompt: 'Design a 10-slide startup pitch deck with slide navigation. Include: title slide, problem, solution, market size, product demo (placeholder), business model, traction, team, ask, and contact slide. Use a bold color palette and large typography. Make slides navigable with arrow keys and dot indicators.',
  },
  {
    id: 'slides-presentation',
    name: 'Presentation',
    category: 'slides',
    description: 'Clean presentation template with multiple layouts',
    prompt: 'Design a professional presentation with 6 slides: title slide, agenda, content with image, two-column comparison, data/chart slide, and closing slide. Include slide navigation, progress indicator, and speaker notes toggle.',
  },
  {
    id: 'component-form',
    name: 'Form Builder',
    category: 'component',
    description: 'Multi-step form with validation and progress indicator',
    prompt: 'Design a multi-step form wizard with 4 steps: Personal Info, Address, Payment, and Review. Include a progress bar, form validation with error states, input fields (text, select, checkbox, radio), and animated step transitions.',
  },
  {
    id: 'component-chat',
    name: 'Chat UI',
    category: 'component',
    description: 'Messaging interface with conversation list and thread',
    prompt: 'Design a chat/messaging interface with: conversation list sidebar with avatars and previews, active chat thread with sent/received message bubbles, typing indicator, message input with attachment button, and online status indicators.',
  },
  {
    id: 'component-kanban',
    name: 'Kanban Board',
    category: 'component',
    description: 'Project board with draggable columns and cards',
    prompt: 'Design a Kanban project board with 4 columns (To Do, In Progress, Review, Done). Each column has 3-5 cards with title, assignee avatar, priority label, and due date. Include an add card button and column headers with card counts.',
  },
  {
    id: 'component-settings',
    name: 'Settings Page',
    category: 'component',
    description: 'App settings with toggles, selects, and sections',
    prompt: 'Design an app settings page with categorized sections: Profile (avatar upload, name, email), Preferences (theme toggle, language select, notification toggles), Security (password change, 2FA toggle), and Danger Zone (delete account). Use clear section separators.',
  },
  {
    id: 'component-ecommerce',
    name: 'Product Page',
    category: 'component',
    description: 'E-commerce product detail with gallery and cart',
    prompt: 'Design an e-commerce product detail page with: image gallery (main image + thumbnails), product title, price, star rating, size/color selectors, quantity picker, Add to Cart button, product description tabs (Details, Reviews, Shipping), and related products carousel.',
  },
];

export const TEMPLATE_CATEGORIES = [
  { id: 'mobile', label: 'Mobile', icon: 'M8 2h8a2 2 0 012 2v16a2 2 0 01-2 2H8a2 2 0 01-2-2V4a2 2 0 012-2zM12 18h.01' },
  { id: 'web', label: 'Web', icon: 'M4 6h16v10H4zM1 18h22' },
  { id: 'slides', label: 'Slides', icon: 'M2 3h20v14H2zM8 21h8M12 17v4' },
  { id: 'component', label: 'Components', icon: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5' },
] as const;
