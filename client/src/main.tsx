import {StrictMode,lazy,Suspense} from 'react';
import {createRoot} from 'react-dom/client';
import {BrowserRouter,NavLink,Route,Routes,Link} from 'react-router-dom';
import {Compass,MessageCircle,FileText,FolderOpen,Sun} from 'lucide-react';
import {Provider,useApp,languages} from './context';
import type {Lang} from './api/types';
import {ErrorBoundary,Loading} from './components';
import Intake from './pages/Intake';
import './styles.css';


const Schemes=lazy(()=>import('./pages/Schemes'));
const Scheme=lazy(()=>import('./pages/Scheme'));
const Explain=lazy(()=>import('./pages/Explain'));
function App(){const {lang,setLang,t}=useApp();return <><header><Link className="brand" to="/"><Sun/><span>Adhikaar<small>अधिकार · A little help. A big step.</small></span></Link><label className="language"><span>{t.language}</span><select value={lang} onChange={e=>setLang(e.target.value as Lang)}>{Object.entries(languages).map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label></header><div className="shell"><nav aria-label="Main navigation">{[['/','home',Compass],['/schemes','schemes',Sun],['/explain','explain',FileText],['/ask','ask',MessageCircle],['/runs','runs',FolderOpen]].map(([path,key,Icon])=>{const C=Icon as typeof Sun;return <NavLink key={path as string} to={path as string} end={path==='/'}><C size={20}/><span>{t[key as keyof typeof t]}</span></NavLink>;})}</nav><main><Suspense fallback={<Loading/>}><Routes><Route path="/" element={<Intake/>}/><Route path="/schemes" element={<Schemes/>}/><Route path="/schemes/:slug" element={<Scheme/>}/><Route path="/explain" element={<Explain/>}/><Route path="*" element={<div className="empty"><h1>Page not found</h1><Link to="/">Go home</Link></div>}/></Routes></Suspense><footer>Adhikaar helps you understand and apply. Eligibility and final decisions belong to the official authority.</footer></main></div></>;}
createRoot(document.getElementById('root')!).render(<StrictMode><ErrorBoundary><BrowserRouter><Provider><App/></Provider></BrowserRouter></ErrorBoundary></StrictMode>);




