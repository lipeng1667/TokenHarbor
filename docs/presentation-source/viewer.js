(()=>{'use strict';
  document.documentElement.classList.add('js');
  const menu=document.querySelector('.contents');
  document.querySelectorAll('.toc a').forEach(link=>link.addEventListener('click',()=>{menu.open=false;}));
  document.addEventListener('click',event=>{if(menu.open&&!menu.contains(event.target))menu.open=false;});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&menu.open){menu.open=false;menu.querySelector('summary').focus();}});
  document.querySelector('.print-button').addEventListener('click',()=>window.print());
  const chapters=[...document.querySelectorAll('.chapter')],links=[...document.querySelectorAll('.toc a')];
  const header=document.querySelector('.masthead'),status=document.querySelector('.reading-status');
  const title=status.querySelector('.reading-title'),number=status.querySelector('.reading-count b');
  const meter=status.querySelector('.reading-meter'),fill=meter.querySelector('i');
  let pending=false;
  function currentSection(){
    const top=header.getBoundingClientRect().height+36;
    let current=null;
    for(const chapter of chapters){if(chapter.getBoundingClientRect().top<=top)current=chapter;else break;}
    links.forEach(link=>{if(current&&link.hash===`#${current.id}`)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');});
    const index=current?chapters.indexOf(current)+1:0,label=current?current.dataset.title:'封面';
    title.textContent=label;title.title=label;
    number.textContent=String(index).padStart(2,'0');
    meter.setAttribute('aria-valuenow',index);
    meter.setAttribute('aria-valuetext',current?`第 ${index} 章，共 ${chapters.length} 章，${label}`:'封面');
    fill.style.width=`${index/chapters.length*100}%`;
  }
  addEventListener('scroll',()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{currentSection();pending=false;});},{passive:true});
  function headerSize(){document.documentElement.style.setProperty('--header-offset',`${header.getBoundingClientRect().height+16}px`);currentSection();}
  addEventListener('resize',headerSize);
  if('ResizeObserver' in window)new ResizeObserver(headerSize).observe(header);
  headerSize();
})();
