import type { ArtifactFile, UnifiedArtifactType } from '@/stores/unifiedArtifactStore';

export interface ArtifactTemplate {
  id: string;
  name: string;
  icon: string;
  category: 'app' | 'document' | 'component';
  description: string;
  type: UnifiedArtifactType;
  files: ArtifactFile[];
}

export const ARTIFACT_TEMPLATES: ArtifactTemplate[] = [
  {
    id: 'tpl-counter',
    name: 'Counter App',
    icon: '\u2795',
    category: 'app',
    description: 'Simple React counter to test the artifact sandbox',
    type: 'app',
    files: [
      {
        path: 'App.jsx',
        type: 'jsx',
        content: `export default function App() {
  const [count, setCount] = React.useState(0);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', fontFamily: 'system-ui', gap: 16 }}>
      <h1 style={{ fontSize: 48, margin: 0 }}>{count}</h1>
      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={() => setCount(c => c - 1)} style={{ padding: '8px 20px', fontSize: 18, borderRadius: 8, border: '1px solid #ccc', cursor: 'pointer' }}>\u2212</button>
        <button onClick={() => setCount(0)} style={{ padding: '8px 20px', fontSize: 18, borderRadius: 8, border: '1px solid #ccc', cursor: 'pointer' }}>Reset</button>
        <button onClick={() => setCount(c => c + 1)} style={{ padding: '8px 20px', fontSize: 18, borderRadius: 8, border: '1px solid #ccc', cursor: 'pointer' }}>+</button>
      </div>
    </div>
  );
}`,
      },
    ],
  },
  {
    id: 'tpl-dashboard',
    name: 'Dashboard',
    icon: '\uD83D\uDCCA',
    category: 'app',
    description: 'Analytics dashboard with KPI cards and chart',
    type: 'app',
    files: [
      {
        path: 'App.jsx',
        type: 'jsx',
        content: `import KPICards from './KPICards';
import Chart from './Chart';

export default function App() {
  return (
    <div style={{ padding: 24, fontFamily: 'system-ui', maxWidth: 960, margin: '0 auto' }}>
      <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 20 }}>Dashboard</h1>
      <KPICards />
      <Chart />
    </div>
  );
}`,
      },
      {
        path: 'KPICards.jsx',
        type: 'jsx',
        content: `const cards = [
  { label: 'Revenue', value: '$12,450', change: '+12%', color: '#10b981' },
  { label: 'Users', value: '1,234', change: '+8%', color: '#3b82f6' },
  { label: 'Orders', value: '342', change: '-3%', color: '#ef4444' },
  { label: 'Conversion', value: '3.2%', change: '+0.4%', color: '#8b5cf6' },
];

export default function KPICards() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16, marginBottom: 24 }}>
      {cards.map(c => (
        <div key={c.label} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: 16 }}>
          <div style={{ fontSize: 13, color: '#6b7280' }}>{c.label}</div>
          <div style={{ fontSize: 28, fontWeight: 700, marginTop: 4 }}>{c.value}</div>
          <div style={{ fontSize: 13, color: c.color, marginTop: 4 }}>{c.change}</div>
        </div>
      ))}
    </div>
  );
}`,
      },
      {
        path: 'Chart.jsx',
        type: 'jsx',
        content: `const data = [40, 55, 45, 65, 60, 80, 75, 90, 85, 95, 88, 100];
const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

export default function Chart() {
  const max = Math.max(...data);
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: 20 }}>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Monthly Revenue</div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 160 }}>
        {data.map((v, i) => (
          <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            <div style={{ width: '100%', background: '#3b82f6', borderRadius: 4, height: (v / max) * 140, transition: 'height 0.3s' }} />
            <span style={{ fontSize: 10, color: '#9ca3af' }}>{months[i]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}`,
      },
    ],
  },
  {
    id: 'tpl-todo',
    name: 'Todo App',
    icon: '\u2705',
    category: 'app',
    description: 'Interactive todo list with add, complete, and delete',
    type: 'app',
    files: [
      {
        path: 'App.jsx',
        type: 'jsx',
        content: `export default function App() {
  const [todos, setTodos] = React.useState([
    { id: 1, text: 'Learn React', done: true },
    { id: 2, text: 'Build an artifact', done: false },
    { id: 3, text: 'Ship it!', done: false },
  ]);
  const [input, setInput] = React.useState('');

  const addTodo = () => {
    if (!input.trim()) return;
    setTodos(prev => [...prev, { id: Date.now(), text: input.trim(), done: false }]);
    setInput('');
  };

  const toggle = (id) => setTodos(prev => prev.map(t => t.id === id ? { ...t, done: !t.done } : t));
  const remove = (id) => setTodos(prev => prev.filter(t => t.id !== id));

  return (
    <div style={{ maxWidth: 480, margin: '40px auto', fontFamily: 'system-ui', padding: 20 }}>
      <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 16 }}>Todos</h1>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && addTodo()}
          placeholder="Add a task..." style={{ flex: 1, padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 14 }} />
        <button onClick={addTodo} style={{ padding: '8px 16px', borderRadius: 8, background: '#3b82f6', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 14 }}>Add</button>
      </div>
      {todos.map(t => (
        <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid #f3f4f6' }}>
          <input type="checkbox" checked={t.done} onChange={() => toggle(t.id)} />
          <span style={{ flex: 1, textDecoration: t.done ? 'line-through' : 'none', color: t.done ? '#9ca3af' : '#111' }}>{t.text}</span>
          <button onClick={() => remove(t.id)} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: 16 }}>\u00d7</button>
        </div>
      ))}
      <div style={{ marginTop: 12, fontSize: 13, color: '#6b7280' }}>{todos.filter(t => !t.done).length} remaining</div>
    </div>
  );
}`,
      },
    ],
  },
  {
    id: 'tpl-landing',
    name: 'Landing Page',
    icon: '\uD83C\uDF10',
    category: 'app',
    description: 'Marketing landing page with hero and features',
    type: 'app',
    files: [
      {
        path: 'index.html',
        type: 'html',
        content: `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, sans-serif; color: #111; }
    .hero { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 80px 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; }
    .hero h1 { font-size: 48px; font-weight: 700; max-width: 600px; }
    .hero p { font-size: 18px; opacity: 0.9; margin-top: 16px; max-width: 500px; }
    .hero .cta { margin-top: 32px; padding: 14px 32px; background: #fff; color: #764ba2; border-radius: 8px; font-weight: 600; font-size: 16px; text-decoration: none; }
    .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 24px; padding: 60px 40px; max-width: 960px; margin: 0 auto; }
    .feature { text-align: center; padding: 24px; }
    .feature .icon { font-size: 40px; margin-bottom: 12px; }
    .feature h3 { font-size: 18px; margin-bottom: 8px; }
    .feature p { font-size: 14px; color: #6b7280; line-height: 1.6; }
  </style>
</head>
<body>
  <div class="hero">
    <h1>Build Something Amazing</h1>
    <p>The fastest way to turn your ideas into interactive prototypes. No code required.</p>
    <a href="#" class="cta">Get Started Free</a>
  </div>
  <div class="features">
    <div class="feature"><div class="icon">\u26A1</div><h3>Lightning Fast</h3><p>Generate production-ready designs in seconds with AI-powered creation.</p></div>
    <div class="feature"><div class="icon">\uD83C\uDFA8</div><h3>Beautiful Design</h3><p>Every artifact follows modern design principles with responsive layouts.</p></div>
    <div class="feature"><div class="icon">\uD83D\uDD27</div><h3>Fully Interactive</h3><p>Real React components that respond to clicks, forms, and state changes.</p></div>
  </div>
</body>
</html>`,
      },
    ],
  },
  {
    id: 'tpl-form',
    name: 'Form Builder',
    icon: '\uD83D\uDCDD',
    category: 'component',
    description: 'Multi-step form with validation',
    type: 'component',
    files: [
      {
        path: 'App.jsx',
        type: 'jsx',
        content: `export default function App() {
  const [step, setStep] = React.useState(0);
  const [data, setData] = React.useState({ name: '', email: '', message: '' });
  const [errors, setErrors] = React.useState({});

  const validate = () => {
    const e = {};
    if (step === 0 && !data.name.trim()) e.name = 'Name is required';
    if (step === 1 && !/\\S+@\\S+\\.\\S+/.test(data.email)) e.email = 'Valid email required';
    if (step === 2 && !data.message.trim()) e.message = 'Message is required';
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const next = () => { if (validate()) setStep(s => Math.min(s + 1, 3)); };
  const back = () => setStep(s => Math.max(s - 1, 0));

  const field = (key, label, type = 'text') => (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4, color: '#374151' }}>{label}</label>
      {type === 'textarea' ? (
        <textarea value={data[key]} onChange={e => setData(d => ({ ...d, [key]: e.target.value }))} rows={4}
          style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: errors[key] ? '1px solid #ef4444' : '1px solid #d1d5db', fontSize: 14, resize: 'vertical' }} />
      ) : (
        <input value={data[key]} onChange={e => setData(d => ({ ...d, [key]: e.target.value }))}
          style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: errors[key] ? '1px solid #ef4444' : '1px solid #d1d5db', fontSize: 14 }} />
      )}
      {errors[key] && <div style={{ color: '#ef4444', fontSize: 12, marginTop: 4 }}>{errors[key]}</div>}
    </div>
  );

  const steps = ['Your Name', 'Email', 'Message', 'Done!'];

  return (
    <div style={{ maxWidth: 440, margin: '40px auto', fontFamily: 'system-ui', padding: 24 }}>
      <div style={{ display: 'flex', gap: 4, marginBottom: 24 }}>
        {steps.map((s, i) => (
          <div key={i} style={{ flex: 1, height: 4, borderRadius: 2, background: i <= step ? '#3b82f6' : '#e5e7eb' }} />
        ))}
      </div>
      <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>{steps[step]}</h2>
      {step === 0 && field('name', 'Full Name')}
      {step === 1 && field('email', 'Email Address')}
      {step === 2 && field('message', 'Your Message', 'textarea')}
      {step === 3 && (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <div style={{ fontSize: 48 }}>\u2705</div>
          <p style={{ marginTop: 12, color: '#6b7280' }}>Thanks, {data.name}! We\u2019ll reach out at {data.email}.</p>
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        {step > 0 && step < 3 && <button onClick={back} style={{ padding: '10px 20px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer', fontSize: 14 }}>Back</button>}
        {step < 3 && <button onClick={next} style={{ padding: '10px 20px', borderRadius: 8, background: '#3b82f6', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 14, marginLeft: 'auto' }}>{step === 2 ? 'Submit' : 'Next'}</button>}
      </div>
    </div>
  );
}`,
      },
    ],
  },
];
