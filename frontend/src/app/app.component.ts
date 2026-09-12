import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <nav>
      <span class="brand">公共收益分摊公示</span>
      <a routerLink="/contracts" routerLinkActive="active">收益合同</a>
      <a routerLink="/versions" routerLinkActive="active">公示版本</a>
    </nav>
    <main><router-outlet /></main>
  `,
})
export class AppComponent {}
